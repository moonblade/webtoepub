#!/usr/bin/python3
import feedparser
import pickle
import time
import subprocess

feeds = [{
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
        self.completedUrls = set([])
        self.getData()
        self.feed = feedparser.parse(feedObj["url"])

    def convert(self):
        for entry in self.feed.entries[::-1]:
            if entry.link not in self.completedUrls and "Protected:" not in entry.title:
                self.epub(entry.link, self.feed.feed.title + " - " + entry.title + "(" + time.strftime("%Y-%m-%d", entry.published_parsed) + ")")
                # print(entry.title, entry.link, entry.published)

    def epub(self, url, title):
        print("Converting: ", title)
        subprocess.check_call('percollate epub ' + url + ' -o "output/' + title +  '.epub" -t "' + title + '"', shell=True)
        subprocess.check_call('book "output/' + title + '.epub"')
        self.complete(url)

    def complete(self, url):
        self.completedUrls.add(url)
        self.saveData()

    def saveData(self):
        with open("completed.db", "wb") as data:
            pickle.dump(self.completedUrls, data)

    def getData(self):
        try:
            with open("completed.db", "rb") as data:
                self.completedUrls = pickle.load(data)
                self.completedUrls.remove("https://wanderinginn.com/2023/04/09/9-41-pt-1/")
        except Exception:
            with open("completed.db", "wb") as data:
                pickle.dump(self.completedUrls, data)



main = Feeds(feeds)
webToEpub = WebToEpub(feeds[0])
