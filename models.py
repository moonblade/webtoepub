from enum import Enum
from pydantic import BaseModel, HttpUrl
from typing import Optional
import time

class FeedItem(BaseModel):
    title: str = ""
    name: str
    url: HttpUrl
    ignore: Optional[bool] = False

    def get_url(self) -> str:
        return str(self.url)

class EntryType(str, Enum):
    wanderinginn = "wanderinginn"
    royalroad = "royalroad"

class Entry(BaseModel):
    title: str
    link: HttpUrl
    entryType: EntryType = EntryType.royalroad
    published_parsed: tuple

    def get_link(self) -> str:
        return str(self.link)

    def get_date(self) -> str:
        return time.strftime("%Y-%m-%d", self.published_parsed)
