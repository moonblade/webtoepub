#!/usr/local/bin/python3
import argparse
import feedparser
import pickle
import time
import subprocess
import ssl
import os
from sys import platform
import requests

parser = argparse.ArgumentParser(prog='WebToEpub', description='Get books from feed list and put them in kindle as epub')
parser.add_argument('-n', '--dry-run', action='store_true')
parser.add_argument('-u', '--no-update-db', action='store_true')
args = parser.parse_args()


class Feeds:
    def __init__(self):
        convertors = []
        r = requests.get('https://browse.moonblade.work/api/public/dl/cVkFNclG?inline=true')
        feeds = r.json()
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
        self.feed = feedparser.parse(feedObj["url"])

    def convert(self):
        for entry in self.feed.entries[::-1]:
            if entry.link not in self.completedUrls and "Protected:" not in entry.title:
                self.epub(entry.link, ((self.feed.feed.title + " - ") if self.feed.feed.title not in entry.title else "")  + time.strftime("%Y-%m-%d", entry.published_parsed) + " - " + entry.title)

    def epub(self, url, title):
        percollatePath = "percollate"
        ebookConvertPath = "ebook-convert"
        if platform == "linux":
            percollatePath = "/home/moonblade/.nvm/versions/node/v19.9.0/bin/percollate"
            ebookConvertPath = "/Applications/calibre.app/Contents/MacOS//ebook-convert"
        print("Downloading: ", title)
        subprocess.check_call(percollatePath + ' epub ' + url + ' -o "output/' + title +  '.epub" -t "' + title + '"', shell=True, cwd=self.scriptPath)
        # subprocess.check_call(percollatePath + ' pdf ' + url + ' -o "output/' + title +  '.pdf" -t "' + title + '"', shell=True, cwd=self.scriptPath)
        # print("\nConverting: ", title)
        # subprocess.check_call(ebookConvertPath + ' "output/' + title +  '.pdf" "output/' + title + '.epub"', shell=True, cwd=self.scriptPath)
        print("\nSending: ", title)
        if (not args.dry_run):
            subprocess.check_call('echo book | mutt -s "' + title + '" -a "output/' + title + '.epub" -- mnishamk95@kindle.com', shell=True, cwd=self.scriptPath)
        print("---")
        if (not args.dry_run and not args.no_update_db):
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



main = Feeds()
