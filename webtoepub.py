#!/usr/local/bin/python3
import feedparser
import pickle
import time
import subprocess
import ssl

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
        ssl._create_default_https_context = ssl._create_unverified_context
        self.feed = feedparser.parse(feedObj["url"])

    def convert(self):
        for entry in self.feed.entries[::-1]:
            if entry.link not in self.completedUrls and "Protected:" not in entry.title:
                self.epub(entry.link, self.feed.feed.title + " - " + time.strftime("%Y-%m-%d", entry.published_parsed) + " - " + entry.title)

    def epub(self, url, title):
        print("Converting: ", title)
        subprocess.check_call('percollate epub ' + url + ' -o "output/' + title +  '.epub" -t "' + title + '"', shell=True)
        print("Sending: ", title)
        subprocess.check_call('echo book | mutt -s "' + title + '" -a "output/' + title + '.epub" -- mnishamk95@kindle.com', shell=True)
        print("---")
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
        except Exception:
            with open("completed.db", "wb") as data:
                pickle.dump(self.completedUrls, data)



main = Feeds(feeds)
