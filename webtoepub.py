#!/usr/bin/python3
import feedparser
import pickle
import time

feeds = [{
    "title": "The Wandering Inn",
    "url": "https://wanderinginn.com/feed/"
}]

class Feeds:
    def __init__(self, feeds):
        convertors = []
        for feed in feeds:
            convertor = WebToEpub(feed)
            convertors.append(convertor)
            convertor.convert()


class WebToEpub:
    def __init__(self,feedObj):
        self.compltedUrls = set([])
        self.getData()
        self.feed = feedparser.parse(feedObj["url"])

    def convert(self):
        for entry in self.feed.entries[::-1]:
            if entry not in self.compltedUrls and "Protected:" not in entry.title:
                self.epub(entry.link, self.feed.feed.title + " - " + entry.title + "(" + time.strftime("%Y-%m-%d", entry.published_parsed) + ")")
                # print(entry.title, entry.link, entry.published)

    def epub(self, url, title):
        print("Converting: ", title)


    def saveData(self):
        with open("completed.db", "wb") as data:
            pickle.dump(self.compltedUrls, data)

    def getData(self):
        try:
            with open("completed.db", "rb") as data:
                self.compltedUrls = pickle.load(data)
        except Exception:
            with open("completed.db", "wb") as data:
                pickle.dump(self.compltedUrls, data)



main = Feeds(feeds)
webToEpub = WebToEpub(feeds[0])
