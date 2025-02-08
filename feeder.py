import json
import os
from time import time
from typing import List
from db import add_entry, has_entry
from models import Entry, EntryType, Feed, FeedItem
import feedparser
import requests
from requests_html import HTMLSession
from bs4 import BeautifulSoup
from utils import custom_logger
from mail import send_gmail
import pypandoc
import re

FEEDURL = os.getenv("FEEDURL", "https://browse.sirius.moonblade.work/api/public/dl/-ZyX3mJU")
WANDERING_INN_URL_FRAGMENT = os.getenv("WANDERING_INN_URL_FRAGMENT", "wanderinginn")
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", "/feeds")
DEBUG_MODE = os.getenv("DEBUG_MODE", "false") == "true"
logger = custom_logger(__name__)

with open("./keywords.txt", 'r') as file:
    KEYWORDS_TO_REMOVE = [line.strip() for line in file if line.strip()]

def get_feed_list() -> List[FeedItem]:
    """
    Retrieves a list of feed items from a given URL, parses the JSON response,
    and returns a list of Pydantic FeedItem objects.
    """
    response = requests.get(FEEDURL)
    response.raise_for_status()
    data = response.json()
    feed = Feed(**data)
    return feed

def download(entry: Entry, feed: FeedItem):
    """
    Downloads the content of an entry to disk.
    """
    feed_path = os.path.join(DOWNLOAD_PATH, feed.title)
    html_download_path = os.path.join(feed_path, "html")
    os.makedirs(feed_path, exist_ok=True)
    os.makedirs(html_download_path, exist_ok=True)
    html_file_path = os.path.join(html_download_path, f"{entry.title}.html")
    if os.path.exists(html_file_path):
        return
    logger.info(f"Downloading content from {entry.link} to {html_file_path}")
    session = HTMLSession()
    response = session.get(entry.link)
    response.raise_for_status()
    with open(html_file_path, "w") as f:
        f.write(response.html.html)
    logger.info(f"Downloaded content {html_file_path}")

def clean_wandering_inn(html_content: str) -> str:
    """
    Cleans the downloaded content of a Wandering Inn entry.
    """
    soup = BeautifulSoup(html_content, "lxml")

    article = soup.find("article")
    if article is None:
        return ""

    entry_content = article.find("div", class_="entry-content")
    if entry_content is None:
        return ""

    # Remove unwanted elements (consistent style)
    for element in entry_content.find_all('div', class_='video-player'):
        element.extract()
    for element in entry_content.find_all('span', class_='embed-youtube'):  # Consistent style
        element.extract()
    for element in entry_content.find_all('img'):
        element.extract()
    for element in entry_content.find_all('div', class_='gallery'):  # Consistent style
        element.extract()

    return entry_content.prettify()

def clean_royal_road(html_content: str, keywords_to_remove: List[str]) -> str:
    """
    Cleans the downloaded content of a Royal Road entry.
    """
    soup = BeautifulSoup(html_content, "lxml")
    chapter_div = soup.find("div", class_="chapter-inner chapter-content")
    if not chapter_div:
        print("Could not find the chapter content div")
        return ""

    extracted = False
    for para in chapter_div.find_all(["p", "div"]):
        text = para.get_text().strip()
        if "." in text and text.count(".") <= 3 and " " in text and text.count(" ") <= 25: #Check for . and space before count
            keywordsFound = 0
            for keyword in keywords_to_remove:
                if keyword.lower() in text.lower():
                    keywordsFound += 1
            if keywordsFound >= 2:
                logger.info(f"Extracted royal road watermark: {text}")
                para.extract()
                extracted = True
                break
    if not extracted:
        logger.warn("Could not find any paragraphs matching criteria")
    return str(chapter_div) if chapter_div else ""

def clean(entry: Entry, feed: FeedItem):
    """
    Cleans the downloaded content of an entry.
    """
    feed_path = os.path.join(DOWNLOAD_PATH, feed.title)
    html_download_path = os.path.join(feed_path, "html")
    html_file_path = os.path.join(html_download_path, f"{entry.title}.html")
    cleaned_download_path = os.path.join(feed_path, "cleaned")
    cleaned_file_path = os.path.join(cleaned_download_path, f"{entry.title}.html")
    os.makedirs(cleaned_download_path, exist_ok=True)
    if os.path.exists(cleaned_file_path):
        return
    logger.info(f"Cleaning content from {html_file_path}")
    with open(html_file_path, "r") as f:
        html_content = f.read()
    if entry.entryType == EntryType.wanderinginn:
        cleaned_html = clean_wandering_inn(html_content)
    elif entry.entryType == EntryType.royalroad:
        cleaned_html = clean_royal_road(html_content, KEYWORDS_TO_REMOVE)
    else:
        cleaned_html = html_content
    with open(cleaned_file_path, "w") as f:
        f.write(cleaned_html)
    logger.info(f"Cleaned content saved to {cleaned_file_path}")

def convert_to_epub(entry: Entry, feed: FeedItem):
    """
    Converts the cleaned content of an entry to an EPUB file.
    """
    feed_path = os.path.join(DOWNLOAD_PATH, feed.title)
    cleaned_html_path = os.path.join(feed_path, "cleaned", f"{entry.title}.html")
    epub_file_path_no_space = os.path.join(feed_path, f"{entry.get_file_name()}.epub")
    epub_file_path = os.path.join(feed_path, f"{entry.title}.epub")
    if os.path.exists(epub_file_path):
        return
    logger.info(f"Converting cleaned content from {cleaned_html_path} to EPUB")

    extra_args = [
        '--metadata', f'title={entry.title}',
        '--metadata', 'lang=en-US',
        '--css', "./epub.css"
    ]

    pypandoc.convert_file(
        cleaned_html_path,
        'epub',
        outputfile=epub_file_path_no_space,
        extra_args=extra_args
    )
    os.rename(epub_file_path_no_space, epub_file_path)
    logger.info(f"EPUB file saved to {epub_file_path}")

def send_email(entry: Entry, feed: FeedItem):
    """
    Sends an email with the EPUB file attached.
    """
    feed_path = os.path.join(DOWNLOAD_PATH, feed.title)
    epub_file_path = os.path.join(feed_path, f"{entry.title}.epub")
    if not os.path.exists(epub_file_path):
        logger.error(f"EPUB file not found: {epub_file_path}")
        return
    if has_entry(entry):
        return
    if feed.dry_run:
        logger.info(f"DRY RUN: Would have sent email with EPUB file: {epub_file_path}")
    else:
        logger.info(f"Sending email with EPUB file: {epub_file_path}")
        send_gmail(
            subject=f"{feed.title} - {entry.title}",
            content=f"EPUB file for {entry.title} is attached.",
            attachment_path=epub_file_path
        )
    entry.time_sent = int(time())
    add_entry(entry, feed)

def process_entry(entry: Entry, feed: FeedItem):
    """
    Processes a single entry in a feed.
    """
    try:
        feed.title = re.sub(r"\[.*?\]", "", feed.title)
        feed.title = feed.title.strip()
        entry.title = re.sub(r"\[.*?\]", "", entry.title)
        entry.title = entry.title.strip()
        if WANDERING_INN_URL_FRAGMENT in entry.link:
            entry.entryType = EntryType.wanderinginn
            entry.title = feed.title + " - " + entry.title
            if entry.ignore():
                logger.info(f"Ignoring entry: {entry.title}")
                return
        entry.title = entry.get_date() + " - " + entry.title
        download(entry, feed)
        clean(entry, feed)
        convert_to_epub(entry, feed)
        send_email(entry, feed)

    except Exception as e:
        logger.exception(f"Error processing entry: {e}")

def process_feed_item(feed: FeedItem):
    """
    Processes a single feed item.
    """
    try:
        if feed.ignore:
            logger.debug(f"Ignoring feed: {feed.name}")
            return
        logger.debug(f"Processing feed - {feed.name}")
        feed_data = feedparser.parse(feed.url)
        feed.title = feed_data.feed.get("title", "")
        entries = feed_data.get("entries", [])
        for entry in entries:
            try:
                entry = Entry(**entry)
                process_entry(entry, feed)
            except Exception as e:
                logger.exception(f"Error processing entry: {e}")
    except Exception as e:
        logger.exception(f"Error processing feed {feed.name}: {e}")

def process_feed(feed: Feed):
    """
    Processes the entire feed.
    """
    if DEBUG_MODE:
        feed.feeds = feed.feeds[:2]
    for feed_item in feed.feeds:
        feed_item.dry_run = feed.dry_run
        process_feed_item(feed_item)

def execute():
    logger.info("Feed processing started.")
    feed = get_feed_list()
    process_feed(feed)
