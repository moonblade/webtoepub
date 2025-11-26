import json
import os
import time
from typing import List
from db import add_entry, has_entry
from models import EmailBatch, Entry, EntryType, Feed, FeedItem
import feedparser
import requests
from requests_html import HTMLSession
from bs4 import BeautifulSoup
from utils import custom_logger
from mail import send_gmail
import pypandoc
import re

FEEDURL = os.getenv("FEEDURL", "https://browse.sirius.moonblade.work/api/public/dl/hf_Ov0yq")
WANDERING_INN_URL_FRAGMENT = os.getenv("WANDERING_INN_URL_FRAGMENT", "wanderinginn")
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", "/feeds")
DEBUG_MODE = os.getenv("DEBUG_MODE", "false") == "true"
MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "20"))
ENTRY_THRESHOLD_FOR_NEW_BOOK = int(os.getenv("ENTRY_THRESHOLD_FOR_NEW_BOOK", "5"))
logger = custom_logger(__name__)

with open("./keywords.txt", 'r') as file:
    KEYWORDS_TO_REMOVE = [line.strip() for line in file if line.strip()]

def get_feed_list() -> List[FeedItem]:
    """
    Retrieves a list of feed items from a given URL, parses the JSON response,
    and returns a list of Pydantic FeedItem objects.
    """
    try:
        response = requests.get(FEEDURL)
        response.raise_for_status()
        data = response.json()
        feed = Feed(**data)
        return feed
    except requests.RequestException as e:
        logger.warn("Returning local feed due to error fetching remote feed.")
        with open("./feed.input.json", 'r') as file:
            data = json.load(file)
            feed = Feed(**data)
            return feed

def sanitize_filename(filename: str) -> str:
    """
    Sanitizes a filename by replacing invalid characters.
    """
    # Replace forward slashes and other problematic characters
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in invalid_chars:
        filename = filename.replace(char, '-')
    return filename

def download(entry: Entry, feed: FeedItem):
    """
    Downloads the content of an entry to disk.
    """
    feed_path = os.path.join(DOWNLOAD_PATH, sanitize_filename(feed.title))
    html_download_path = os.path.join(feed_path, "html")
    os.makedirs(feed_path, exist_ok=True)
    os.makedirs(html_download_path, exist_ok=True)
    html_file_path = os.path.join(html_download_path, f"{sanitize_filename(entry.title)}.html")
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
    for para in chapter_div.find_all(["p", "div", "span"]):
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
    feed_path = os.path.join(DOWNLOAD_PATH, sanitize_filename(feed.title))
    html_download_path = os.path.join(feed_path, "html")
    html_file_path = os.path.join(html_download_path, f"{sanitize_filename(entry.title)}.html")
    cleaned_download_path = os.path.join(feed_path, "cleaned")
    cleaned_file_path = os.path.join(cleaned_download_path, f"{sanitize_filename(entry.title)}.html")
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
    feed_path = os.path.join(DOWNLOAD_PATH, sanitize_filename(feed.title))
    cleaned_html_path = os.path.join(feed_path, "cleaned", f"{sanitize_filename(entry.title)}.html")
    epub_file_path_no_space = os.path.join(feed_path, f"{sanitize_filename(entry.get_file_name())}.epub")
    epub_file_path = os.path.join(feed_path, f"{sanitize_filename(entry.title)}.epub")
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

def prepare_email(entry: Entry, feed: FeedItem):
    """
    Prepares an email for sending by validating the EPUB file exists and entry hasn't been sent.
    Returns None if the email shouldn't be sent.
    """
    feed_path = os.path.join(DOWNLOAD_PATH, sanitize_filename(feed.title))
    epub_file_path = os.path.join(feed_path, f"{sanitize_filename(entry.title)}.epub")
    
    if not os.path.exists(epub_file_path):
        logger.error(f"EPUB file not found: {epub_file_path}")
        return None
    if has_entry(entry):
        return None
    return EmailBatch(entry=entry, feed=feed, epub_path=epub_file_path)

def send_batch_emails(email_batch: List[EmailBatch], feed: Feed):
    """
    Sends all emails in the batch and records them in the database.
    """

    if len(email_batch) > MAX_BATCH_SIZE:
        logger.error(f"Email batch size ({len(email_batch)}) exceeds maximum allowed ({MAX_BATCH_SIZE}). No emails will be sent.")
        for batch in email_batch:
            if batch.feed.dry_run:
                add_entry(batch.entry, batch.feed)
        return

    if len(email_batch) == 0:
        return

    logger.info(f"Preparing to send {len(email_batch)} emails")
    
    if feed.dry_run:
        for batch in email_batch:
            logger.info(f"DRY RUN: Would have sent email with EPUB file: {batch.epub_path}")
            add_entry(batch.entry, batch.feed)
    else:
        for batch in email_batch:
            logger.info(f"Sending email with EPUB file: {batch.epub_path}")
            send_gmail(
                subject=f"{batch.feed.title} - {batch.entry.title}",
                content=f"EPUB file for {batch.entry.title} is attached.",
                attachment_path=batch.epub_path
            )
            batch.entry.time_sent = int(time.time())
            add_entry(batch.entry, batch.feed)

def send_email(entry: Entry, feed: FeedItem):
    """
    Sends an email with the EPUB file attached.
    """
    feed_path = os.path.join(DOWNLOAD_PATH, sanitize_filename(feed.title))
    epub_file_path = os.path.join(feed_path, f"{sanitize_filename(entry.title)}.epub")
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
    entry.time_sent = int(time.time())
    add_entry(entry, feed)

def get_royal_road_chapters(feed_url: str) -> List[Entry]:
    """
    Scrapes the Royal Road table of contents page to get all chapter links.
    Extracts the fiction ID from the RSS feed URL and constructs the main page URL.
    """
    try:
        # Extract fiction ID from RSS URL (e.g., /fiction/syndication/36049 -> 36049)
        fiction_id_match = re.search(r'/fiction/syndication/(\d+)', feed_url)
        if not fiction_id_match:
            logger.error(f"Could not extract fiction ID from URL: {feed_url}")
            return []
        
        fiction_id = fiction_id_match.group(1)
        fiction_url = f"https://www.royalroad.com/fiction/{fiction_id}"
        
        logger.info(f"Scraping Royal Road table of contents from {fiction_url}")
        
        session = HTMLSession()
        response = session.get(fiction_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.html.html, "lxml")
        
        # Find the table of contents - Royal Road uses <table id="chapters">
        chapters_table = soup.find("table", id="chapters")
        if not chapters_table:
            logger.error("Could not find chapters table on Royal Road page")
            return []
        
        # Get the book title
        title_element = soup.find("h1", class_="font-white")
        book_title = title_element.get_text(strip=True) if title_element else "Unknown Book"
        
        entries = []
        # Find all chapter rows in the table
        chapter_rows = chapters_table.find_all("tr")
        
        for row in chapter_rows:
            # Find the link in the row
            link = row.find("a", href=re.compile(r"/fiction/\d+/[^/]+/chapter/\d+"))
            if not link:
                continue
                
            chapter_url = "https://www.royalroad.com" + link['href']
            chapter_title = link.get_text(strip=True)
            
            # Create Entry object with current timestamp for published_parsed
            entry = Entry(
                title=chapter_title,
                link=chapter_url,
                entryType=EntryType.royalroad,
                published_parsed=time.localtime()
            )
            entries.append(entry)
        
        logger.info(f"Found {len(entries)} chapters on Royal Road table of contents")
        return entries
        
    except Exception as e:
        logger.exception(f"Error scraping Royal Road table of contents: {e}")
        return []

def process_entry(entry: Entry, feed: FeedItem, skip_email_prep: bool = False, skip_date: bool = False):
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
        if not skip_date:
            entry.title = entry.get_date() + " - " + entry.title
        download(entry, feed)
        clean(entry, feed)
        convert_to_epub(entry, feed)
        if skip_email_prep:
            return None
        return prepare_email(entry, feed)

    except Exception as e:
        logger.exception(f"Error processing entry: {e}")

def create_compiled_ebook(entries: List[Entry], feed: FeedItem):
    """
    Creates a single compiled ebook from multiple entries.
    """
    feed_path = os.path.join(DOWNLOAD_PATH, sanitize_filename(feed.title))
    compiled_epub_filename = f"{sanitize_filename(feed.title)}_compiled.epub"
    compiled_epub_path = os.path.join(feed_path, compiled_epub_filename)
        
    logger.info(f"Creating compiled ebook for {feed.title} with {len(entries)} chapters")
    
    # Create a combined HTML file with chapter titles
    compiled_html_path = os.path.join(feed_path, "compiled_temp.html")
    
    try:
        with open(compiled_html_path, "w") as compiled_file:
            compiled_file.write("<html><body>\n")
            
            # Entries should already be in oldest-first order
            for entry in entries:
                cleaned_html_path = os.path.join(feed_path, "cleaned", f"{sanitize_filename(entry.title)}.html")
                if os.path.exists(cleaned_html_path):
                    # Add chapter title as h1 heading
                    compiled_file.write(f"<h1>{entry.title}</h1>\n")
                    
                    # Read and append chapter content
                    with open(cleaned_html_path, "r") as chapter_file:
                        chapter_content = chapter_file.read()
                        compiled_file.write(chapter_content)
                        compiled_file.write("\n")
            
            compiled_file.write("</body></html>")
        
        # Convert the combined HTML to EPUB
        compiled_epub_path_no_space = os.path.join(feed_path, f"{feed.title.replace(' ', '_')}_compiled.epub")
        
        extra_args = [
            '--metadata', f'title={feed.title} - Complete',
            '--metadata', 'lang=en-US',
            '--css', "./epub.css",
            '--toc-depth=1'
        ]
        
        pypandoc.convert_file(
            compiled_html_path,
            'epub',
            outputfile=compiled_epub_path_no_space,
            extra_args=extra_args
        )
        os.rename(compiled_epub_path_no_space, compiled_epub_path)
        
        # Clean up temporary file
        os.remove(compiled_html_path)
        
        logger.info(f"Compiled EPUB file saved to {compiled_epub_path}")
        return compiled_epub_path
    except Exception as e:
        logger.exception(f"Error creating compiled ebook: {e}")
        # Clean up temporary file on error
        if os.path.exists(compiled_html_path):
            os.remove(compiled_html_path)
        return None

def process_feed_item(feed: FeedItem):
    """
    Processes a single feed item.
    """
    email_batch = []
    try:
        if feed.ignore:
            logger.debug(f"Ignoring feed: {feed.name}")
            return email_batch

        logger.debug(f"Processing feed - {feed.name}")
        feed_data = feedparser.parse(feed.url)
        feed.title = feed_data.feed.get("title", "")
        entries = feed_data.get("entries", [])
        
        # Check how many unprocessed entries there are
        unprocessed_entries = []
        for entry in entries:
            try:
                entry = Entry(**entry)
                if not has_entry(entry):
                    unprocessed_entries.append(entry)
            except Exception as e:
                logger.exception(f"Error checking entry: {e}")
        
        # Special logic for new books with many unprocessed entries
        if len(unprocessed_entries) > ENTRY_THRESHOLD_FOR_NEW_BOOK:
            logger.info(f"Detected new book with {len(unprocessed_entries)} unprocessed entries (>{ENTRY_THRESHOLD_FOR_NEW_BOOK}). Creating compiled ebook.")
            
            # Store original RSS feed entries before potentially replacing them
            original_rss_entries = unprocessed_entries.copy()
            
            # For Royal Road books, scrape the table of contents to get all chapters
            if "royalroad.com" in feed.url:
                logger.info("Royal Road feed detected. Scraping table of contents for complete book.")
                all_chapters = get_royal_road_chapters(feed.url)
                if all_chapters:
                    # Filter to only unprocessed chapters and reverse to get oldest first
                    unprocessed_entries = [entry for entry in all_chapters if not has_entry(entry)]
                    logger.info(f"Found {len(unprocessed_entries)} unprocessed chapters from Royal Road TOC")
                    
                    # If TOC has no unprocessed entries, mark original RSS entries as processed to avoid reprocessing
                    if len(unprocessed_entries) == 0:
                        logger.info("No unprocessed chapters from TOC. Marking original RSS entries as processed.")
                        for entry in original_rss_entries:
                            entry.time_sent = int(time.time())
                            add_entry(entry, feed)
                        return email_batch
            
            # Process all entries without preparing individual emails
            processed_entries = []
            for entry in unprocessed_entries:
                try:
                    process_entry(entry, feed, skip_email_prep=True, skip_date=True)
                    processed_entries.append(entry)
                except Exception as e:
                    logger.exception(f"Error processing entry: {e}")
            
            # Create compiled ebook
            compiled_epub_path = create_compiled_ebook(processed_entries, feed)
            
            if compiled_epub_path and os.path.exists(compiled_epub_path):
                # Create a single email batch for the compiled ebook
                # Use the first entry as representative
                if processed_entries:
                    representative_entry = processed_entries[0]
                    representative_entry.title = f"{feed.title} - Complete ({len(processed_entries)} chapters)"
                    email_batch.append(EmailBatch(
                        entry=representative_entry,
                        feed=feed,
                        epub_path=compiled_epub_path
                    ))
            
            # Mark all entries as processed regardless of email batch creation
            # This prevents treating it as a new book on next run
            for entry in processed_entries:
                entry.time_sent = int(time.time())
                add_entry(entry, feed)
            logger.info(f"Marked {len(processed_entries)} chapters as processed")
        else:
            # Normal processing for regular updates
            for entry in entries:
                try:
                    entry = Entry(**entry)
                    batch = process_entry(entry, feed)
                    if batch:
                        email_batch.append(batch)
                except Exception as e:
                    logger.exception(f"Error processing entry: {e}")
    except Exception as e:
        logger.exception(f"Error processing feed {feed.name}: {e}")
    return email_batch

def process_feed(feed: Feed):
    """
    Processes the entire feed.
    """
    if DEBUG_MODE:
        feed.feeds = feed.feeds[:2]
        feed.dry_run = True
    all_email_batches = []
    for feed_item in feed.feeds:
        if feed.dry_run:
            feed_item.dry_run = feed.dry_run
        email_batches = process_feed_item(feed_item)
        all_email_batches.extend(email_batches)
    send_batch_emails(all_email_batches, feed)

def execute():
    # check to see if file system is mounted
    test_file = os.getenv("TEST_FILE", "" )
    if test_file and not os.path.exists(test_file):
        logger.error(f"Test file not found: {test_file}")
        return
    logger.info("Feed processing started.")
    feed = get_feed_list()
    process_feed(feed)

if __name__ == "__main__":
    # Test with a smaller feed list
    test_feed_data = {
        "dry_run": True,
        "feeds": [
            {
                "name": "Primal Hunter",
                "url": "https://www.royalroad.com/fiction/syndication/36049"
            }
        ]
    }
    test_feed = Feed(**test_feed_data)
    process_feed(test_feed)
