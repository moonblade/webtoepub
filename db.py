import os
import time
from models import Entry, FeedItem
from tinydb import TinyDB, Query

DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", "/feeds")

if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

db = TinyDB(os.path.join(DOWNLOAD_PATH, 'db.json'))

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
