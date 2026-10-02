import os
import re
import time
import json
from models import Entry, FeedItem
from tinydb import TinyDB, Query
from utils import custom_logger

logger = custom_logger(__name__)

_RR_CHAPTER_ID_RE = re.compile(r'/chapter/(\d+)')

def _normalise_link(link: str) -> str:
    """
    Normalise a Royal Road chapter URL to its canonical short form so that
    RSS links (/fiction/chapter/12345) and TOC-scraped links
    (/fiction/36049/slug/chapter/12345/slug) resolve to the same key.

    Non-RR URLs are returned unchanged.
    """
    m = _RR_CHAPTER_ID_RE.search(link)
    if m:
        return f"https://www.royalroad.com/fiction/chapter/{m.group(1)}"
    return link

CONFIG_PATH = os.getenv("CONFIG_PATH", "/config")

if not os.path.exists(CONFIG_PATH):
    os.makedirs(CONFIG_PATH)

db = TinyDB(os.path.join(CONFIG_PATH, 'db.json'))
feeds_table = db.table('feeds')

# In-memory title index populated by sync_from_imap().
# Maps normalised_subject -> sent_timestamp for legacy emails (no URL in subject).
# Checked by has_entry() as a fast local alternative to per-entry IMAP calls.
# LEGACY — only populated until 2026-12-02.
_imap_title_index: dict = {}


def add_entry(entry: Entry, feed: FeedItem):
    """
    Adds an entry to the database.
    """
    entry_dict = entry.dict()
    entry_dict["link"] = _normalise_link(entry_dict["link"])
    entry_dict["feed"] = feed.dict()
    db.insert(entry_dict)


def has_entry(entry: Entry, feed_title: str = "") -> bool:
    """
    Checks if an entry has already been sent.

    1. DB URL match  — exact lookup on entry.link.
    2. In-memory title match — against _imap_title_index (legacy emails, no URL
       in subject). Tries multiple title formats to match how subjects were
       composed: raw title, feed-prefixed, date-prefixed, and both combined.
       LEGACY FALLBACK — expires 2026-12-02.
    """
    EntryQuery = Query()
    current_time = int(time.time())
    norm_link = _normalise_link(entry.link)

    # Primary: exact URL match in DB (normalised so RSS and TOC URLs both match)
    if db.contains(
        (EntryQuery.link == norm_link) &
        ((EntryQuery.time_sent != 0) |
         ((EntryQuery.time_sent == 0) & (EntryQuery.patreon_lock > current_time)))
    ):
        return True

    # LEGACY FALLBACK — expires 2026-12-02. Remove this block after that date.
    if _imap_title_index and time.time() < 1796169600:  # 2026-12-02 00:00:00 UTC
        raw = entry.title.lower().strip()
        # Build the set of title forms that could appear as a subject suffix:
        #   - raw RSS title:                  "chapter 327: mirror sky"
        #   - with feed prefix:               "the legend of william oh - chapter 327: mirror sky"
        # The IMAP index also stores date-stripped variants so we don't need to
        # add date forms here — they're already covered by _date_variants().
        candidates = {raw}
        if feed_title:
            candidates.add(f"{feed_title.lower().strip()} - {raw}")

        for subject in _imap_title_index:
            for candidate in candidates:
                if subject.endswith(candidate):
                    return True

    return False


def sync_from_imap() -> int:
    """
    One-shot IMAP sync called once at the start of each feeder run.

    - Scans Gmail Sent folder.
    - For new-style emails (URL in subject): inserts URL stubs into TinyDB so
      has_entry() finds them via exact URL match on future entries.
    - For legacy emails (no URL in subject): loads the title index into the
      in-memory _imap_title_index dict so has_entry() can do fast local
      title-suffix matching without further IMAP calls.

    Returns the number of URL stubs inserted into TinyDB.
    """
    global _imap_title_index

    try:
        from gmail_imap import fetch_sent_indexes
    except ImportError:
        logger.warning("gmail_imap not available, skipping IMAP sync.")
        return 0

    try:
        indexes = fetch_sent_indexes(force_refresh=True)
    except Exception as e:
        logger.warning(f"IMAP sync failed: {e}")
        return 0

    EntryQuery = Query()
    inserted = 0

    # URL stubs → persist to DB (new-style emails only, currently 0 but future-proof)
    for url, ts in indexes["url"].items():
        if not db.contains(EntryQuery.link == url):
            stub = {
                "title": "",
                "link": url,
                "entryType": "royalroad",
                "published_parsed": list(time.localtime(ts)),
                "time_sent": ts,
                "patreon_lock": 0,
                "feed": {},
            }
            db.insert(stub)
            inserted += 1

    # Title index → in-memory only (legacy emails, LEGACY until 2026-12-02)
    if time.time() < 1796169600:  # 2026-12-02 00:00:00 UTC
        _imap_title_index = indexes["title"]
        logger.info(
            f"IMAP sync complete: {inserted} URL stubs inserted, "
            f"{len(_imap_title_index)} legacy titles loaded into memory."
        )
    else:
        _imap_title_index = {}
        logger.info(f"IMAP sync complete: {inserted} URL stubs inserted.")

    return inserted

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
    EntryQuery = Query()
    norm_link = _normalise_link(link)
    result = db.remove(EntryQuery.link == norm_link)
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
