import os
import time
import json
from models import Entry, FeedItem
from tinydb import TinyDB, Query

CONFIG_PATH = os.getenv("CONFIG_PATH", "/config")

if not os.path.exists(CONFIG_PATH):
    os.makedirs(CONFIG_PATH)

db = TinyDB(os.path.join(CONFIG_PATH, 'db.json'))
feeds_table = db.table('feeds')

def add_entry(entry: Entry, feed: FeedItem):
    """
    Adds an entry to the database.
    """
    entry_dict = entry.dict()
    entry_dict["feed"] = feed.dict()
    db.insert(entry_dict)

def has_entry(entry: Entry) -> bool:
    """
    Checks if an entry exists in the database.
    """
    Entry = Query()
    current_time = int(time.time())
    response = db.contains(
        (Entry.link == entry.link) & 
        ((Entry.time_sent != 0) | 
         ((Entry.time_sent == 0) & (Entry.patreon_lock > current_time)))
    )
    return response

def get_entries() -> list[Entry]:
    """
    Gets all entries from the database sorted by entry.time_sent in descending order.
    """
    entries = db.all()
    return [Entry(**entry) for entry in sorted(entries, key=lambda x: x["time_sent"], reverse=True)]

def delete_entry(link: str) -> bool:
    """
    Deletes an entry from the database by link.
    Returns True if entry was deleted, False otherwise.
    """
    Entry = Query()
    result = db.remove(Entry.link == link)
    return len(result) > 0


# ============== Feed Management Functions ==============

def get_all_feeds() -> list[FeedItem]:
    """
    Gets all feeds from the feeds table.
    """
    records = feeds_table.all()
    return [FeedItem(**r) for r in records]


def get_feed_by_url(url: str) -> FeedItem | None:
    """
    Gets a single feed by its URL.
    """
    q = Query()
    record = feeds_table.get(q.url == url)
    return FeedItem(**record) if record else None


def add_feed(feed: FeedItem) -> bool:
    """
    Adds a new feed to the feeds table.
    Returns False if feed with same URL already exists.
    """
    q = Query()
    if feeds_table.contains(q.url == feed.url):
        return False
    feeds_table.insert(feed.dict())
    return True


def update_feed(url: str, updates: dict) -> bool:
    """
    Updates a feed by URL.
    updates: dict of fields to set, e.g. {'name': 'New Name', 'ignore': True}
    Returns True if at least one document was updated.
    """
    q = Query()
    result = feeds_table.update(updates, q.url == url)
    return len(result) > 0


def delete_feed(url: str) -> bool:
    """
    Deletes a feed by URL.
    Returns True if feed was deleted, False otherwise.
    """
    q = Query()
    removed = feeds_table.remove(q.url == url)
    return len(removed) > 0


def migrate_feeds_from_json(json_path: str = "feed.input.json") -> int:
    """
    Migrates feeds from feed.input.json to the feeds table.
    Only runs if the feeds table is empty.
    Returns the number of feeds migrated.
    """
    # Only migrate if feeds table is empty
    if feeds_table.all():
        return 0
    
    # Try to load from the json file
    if not os.path.exists(json_path):
        return 0
    
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        feeds = data.get('feeds', [])
        global_dry_run = data.get('dry_run', False)
        
        migrated = 0
        for feed_data in feeds:
            # Apply global dry_run if not set per-feed
            if 'dry_run' not in feed_data:
                feed_data['dry_run'] = global_dry_run
            
            feed = FeedItem(**feed_data)
            feeds_table.insert(feed.dict())
            migrated += 1
        
        return migrated
    except (json.JSONDecodeError, Exception):
        return 0
