from enum import Enum
from pydantic import BaseModel, HttpUrl
from typing import Optional
import time

class FeedItem(BaseModel):
    title: str = ""
    name: str
    url: str
    ignore: Optional[bool] = False
    dry_run: Optional[bool] = False
    time_sent: Optional[int] = 0

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

    def get_date(self) -> str:
        return time.strftime("%Y-%m-%d", self.published_parsed)

    def ignore(self) -> bool:
        return "Patron Early Access:" in self.title

    def get_file_name(self) -> str:
        return self.title.replace(" ", "_")
