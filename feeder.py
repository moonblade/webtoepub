import json
import os
from typing import List
from models import Entry, EntryType, FeedItem
import feedparser
import requests
from requests_html import HTMLSession
from bs4 import BeautifulSoup
from utils import custom_logger


FEEDURL = os.getenv("FEEDURL", "https://browse.sirius.moonblade.work/api/public/dl/-ZyX3mJU")
WANDERING_INN_URL_FRAGMENT = os.getenv("WANDERING_INN_URL_FRAGMENT", "wanderinginn")
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", "/tmp/feeds")
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

    feed_list: List[FeedItem] = []
    for item in data:
        try:
            feed_item = FeedItem(**item)
            feed_list.append(feed_item)
        except Exception as e:
            logger.exception(f"Error creating FeedItem from: {item}. Error: {e}")
            continue
    return feed_list

def download(entry: Entry, feed: FeedItem):
    """
    Downloads the content of an entry to disk.
    """
    feed_path = os.path.join(DOWNLOAD_PATH, feed.name)
    if not os.path.exists(feed_path):
        os.makedirs(feed_path, exist_ok=True)
    html_download_path = os.path.join(feed_path, "html")
    if not os.path.exists(html_download_path):
        os.makedirs(html_download_path, exist_ok=True)
    html_file_path = os.path.join(html_download_path, f"{entry.title}.html")
    if os.path.exists(html_file_path):
        return
    logger.info(f"Downloading content from {entry.get_link()} to {html_file_path}")
    session = HTMLSession()
    response = session.get(entry.get_link())
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
    try:
        feed_path = os.path.join(DOWNLOAD_PATH, feed.name)
        html_download_path = os.path.join(feed_path, "html")
        html_file_path = os.path.join(html_download_path, f"{entry.title}.html")
        cleaned_download_path = os.path.join(feed_path, "cleaned")
        if os.path.exists(cleaned_download_path):
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
        if not os.path.exists(cleaned_download_path):
            os.makedirs(cleaned_download_path, exist_ok=True)
        cleaned_file_path = os.path.join(cleaned_download_path, f"{entry.title}.html")
        with open(cleaned_file_path, "w") as f:
            f.write(cleaned_html)
        logger.info(f"Cleaned content saved to {cleaned_file_path}")
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")


def process_entry(entry: Entry, feed: FeedItem):
    """
    Processes a single entry in a feed.
    """
    try:
        if WANDERING_INN_URL_FRAGMENT in entry.get_link():
            entry.entryType = "wanderinginn"
            entry.title = feed.title + " - " + entry.title
            if entry.ignore():
                logger.info(f"Ignoring entry: {entry.title}")
                return
        entry.title = entry.get_date() + " - " + entry.title
        download(entry, feed)
        clean(entry, feed)

    except Exception as e:
        logger.exception(f"Error processing entry: {e}")

def process_feed(feed: FeedItem):
    """
    Processes a single feed item.
    """
    try:
        if feed.ignore:
            logger.warn(f"Ignoring feed: {feed.name}")
            return
        logger.info(f"Processing feed - {feed.name}")
        feed_data = feedparser.parse(feed.get_url())
        feed.title = feed_data.feed.get("title", "")
        entries = feed_data.get("entries", [])
        for entry in entries[:2]:
            try:
                entry = Entry(**entry)
                process_entry(entry, feed)
            except Exception as e:
                logger.exception(f"Error processing entry: {e}")
    except Exception as e:
        logger.exception(f"Error processing feed {feed.name}: {e}")

def execute():
    feed_list = get_feed_list()
    for feed in feed_list[:2]:
        process_feed(feed)
