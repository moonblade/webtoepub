from enum import Enum
from pydantic import BaseModel, HttpUrl
from typing import Optional
import time
import os  # Added for environment variable access

PATREON_LOCK_HOURS = int(os.environ.get("PATREON_LOCK_HOURS", 4))  # Default to 4 hours


class FeedItem(BaseModel):
    title: str = ""
    name: str
    url: str
    ignore: Optional[bool] = False
    dry_run: Optional[bool] = False

class Feed(BaseModel):
    feeds: list[FeedItem]
    dry_run: bool = False

class EntryType(str, Enum):
    wanderinginn = "wanderinginn"
    royalroad = "royalroad"

class Entry(BaseModel):
    title: str
    link: str
    entryType: EntryType = EntryType.royalroad
    published_parsed: tuple
    time_sent: Optional[int] = 0
    patreon_lock: Optional[int] = 0

    def get_date(self) -> str:
        return time.strftime("%Y-%m-%d", self.published_parsed)

    def set_patreon_lock(self):
        """Sets the patreon lock to current time + PATREON_LOCK_HOURS (in seconds)"""
        self.patreon_lock = int(time.time()) + PATREON_LOCK_HOURS * 3600

    def ignore(self) -> bool:
        if "Patron Early Access:" in self.title:
            return True
        # Check if patreon_lock exists and hasn't expired yet
        if self.patreon_lock and self.patreon_lock > 0:
            return int(time.time()) < self.patreon_lock
        return False

    def get_file_name(self) -> str:
        return self.title.replace(" ", "_")

class EmailBatch(BaseModel):
    entry: Entry
    feed: FeedItem
    epub_path: str
