#!/usr/local/bin/python3
import argparse
import feedparser
from bs4 import BeautifulSoup
import pickle
import time
import subprocess
from requests_html import HTMLSession
import ssl
import os
import json

parser = argparse.ArgumentParser(prog='WebToEpub', description='Get books from feed list and put them in kindle as epub')
parser.add_argument('-n', '--dry-run', action='store_true')
parser.add_argument('-u', '--update-db', action='store_true')
parser.add_argument('-l', '--link', default=None)
args = parser.parse_args()

scriptPath = os.path.dirname(os.path.abspath( __file__ ))

class Feeds:
    def __init__(self):
        convertors = []
        with open(os.path.join(scriptPath, "feed.input.json"), "r") as f:
            feeds = json.load(f)
            for feed in feeds:
                convertor = WebToEpub(feed)
                convertors.append(convertor)
                convertor.convert()


class WebToEpub:
    def __init__(self,feedObj):
        self.completedUrls = set([])
        self.scriptPath = "~"
        self.getData()
        ssl._create_default_https_context = ssl._create_unverified_context
        self.feed = None
        if ("url" in feedObj):
            self.feed = feedparser.parse(feedObj["url"])

    def convert(self):
        if not self.feed:
            return
        for entry in self.feed.entries[::-1]:
            if entry.link not in self.completedUrls and "Patron Early Access:" not in entry.title:
                self.epub(entry.link, ((self.feed.feed.title + " - ") if self.feed.feed.title not in entry.title else "")  + time.strftime("%Y-%m-%d", entry.published_parsed) + " - " + entry.title)

    def clean(self, url, html):
        cleanedHtml = html
        if ("royalroad" in url):
            cleanedHtml = cleanedHtml.find(".chapter-inner.chapter-content")[0]
            return str(cleanedHtml.html)

        if ("wanderinginn" in url):
            cleanedHtml = cleanedHtml.find("article")[0]
            cleanedHtml = cleanedHtml.find(".entry-content")[0]
            soup = BeautifulSoup(str(cleanedHtml.html), features="lxml")
            for video in soup.find_all("div", {"class": "video-player"}):
                video.extract()
            for img in soup.find_all("img", {"class": "alignnone"}):
                img.extract()
            return soup.prettify()

        return cleanedHtml.html

    def epub(self, url, title):
        print("Downloading: ", title)
        session = HTMLSession()
        r = session.get(url)
        htmlContent = self.clean(url, r.html)
        with open("/tmp/article.html", "w") as file:
            file.write(htmlContent)
        subprocess.check_call('pandoc /tmp/article.html -o "output/' + title +  '.epub" --metadata title="' + title + '" --metadata lang="en-US"', shell=True, cwd=self.scriptPath)
        if (not args.dry_run):
            print("\nSending: ", title)
            subprocess.check_call('echo book | mutt -s "' + title + '" -a "output/' + title + '.epub" -- mnishamk95@kindle.com', shell=True, cwd=self.scriptPath)
        print("---")
        if (not args.dry_run or args.update_db):
            self.complete(url)

    def complete(self, url):
        self.completedUrls.add(url)
        self.saveData()

    def saveData(self):
        with open(os.path.join(self.scriptPath, "completed.db"), "wb") as data:
            pickle.dump(self.completedUrls, data)

    def getData(self):
        self.scriptPath = os.path.dirname(os.path.abspath( __file__ ))
        try:
            with open(os.path.join(self.scriptPath, "completed.db"), "rb") as data:
                self.completedUrls = pickle.load(data)
        except Exception:
            with open(os.path.join(self.scriptPath, "completed.db"), "wb") as data:
                pickle.dump(self.completedUrls, data)

def removeLink():
    with open(os.path.join(scriptPath, "completed.db"), "rb") as data:
        completedUrls = pickle.load(data)
    if args.link in completedUrls:
        completedUrls.remove(args.link)
    with open(os.path.join(scriptPath, "completed.db"), "wb") as data:
        pickle.dump(completedUrls, data)

def main():
    if args.link:
        if args.update_db:
            removeLink()
    else:
        Feeds()

if __name__ == "__main__":
    main()
