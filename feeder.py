import json
import os
from typing import List
from models import Entry, FeedItem
import feedparser
import requests

feedurl = os.getenv("FEEDURL", "https://browse.sirius.moonblade.work/api/public/dl/-ZyX3mJU")
wandering_inn_url_fragment = os.getenv("WANDERING_INN_URL_FRAGMENT", "wanderinginn")

def get_feed_list() -> List[FeedItem]:
    """
    Retrieves a list of feed items from a given URL, parses the JSON response,
    and returns a list of Pydantic FeedItem objects.
    """
    try:
        response = requests.get(feedurl)
        response.raise_for_status()
        data = response.json()

        feed_list: List[FeedItem] = []
        for item in data:
            try:
                feed_item = FeedItem(**item)
                feed_list.append(feed_item)
            except Exception as e:
                print(f"Error creating FeedItem from: {item}. Error: {e}")
                continue
        return feed_list
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from {feedurl}: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []

def process_entry(entry: Entry, feed: FeedItem):
    """
    Processes a single entry in a feed.
    """
    try:
        if wandering_inn_url_fragment in entry.get_link():
            entry.entryType = "wanderinginn"
            entry.title = feed.title + " - " + entry.title
        entry.title = entry.get_date() + " - " + entry.title
        print(f"Processing entry: {entry.title} - {entry.link}")


    except Exception as e:
        print(f"Error processing entry: {e}")

def process_feed(feed: FeedItem):
    """
    Processes a single feed item.
    """
    try:
        if feed.ignore:
            print(f"Ignoring feed: {feed.name}")
            return
        print(f"Processing feed: {feed.name} - {feed.url}")
        feed_data = feedparser.parse(feed.get_url())
        feed.title = feed_data.feed.get("title", "")
        entries = feed_data.get("entries", [])
        for entry in entries:
            entry = Entry(**entry)
            process_entry(entry, feed)
        # print(json.dumps(entries, indent=2))
        # Implement feed processing logic
    except Exception as e:
        print(f"Error processing feed {feed.name}: {e}")

def execute():
    feed_list = get_feed_list()
    for feed in feed_list[:2]:
        process_feed(feed)
