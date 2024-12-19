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
import epub

script_dir = os.path.dirname(os.path.abspath(__file__))
filename = os.path.join(script_dir, 'keywords.txt')

with open(filename, 'r') as file:
    KEYWORDS_TO_REMOVE = [line.strip() for line in file if line.strip()]

parser = argparse.ArgumentParser(prog='WebToEpub', description='Get books from feed list and put them in kindle as epub')
parser.add_argument('-n', '--dry-run', action='store_true')
parser.add_argument('-u', '--update-db', action='store_true')
parser.add_argument('-i', '--remove-images', action='store_true')
parser.add_argument('-l', '--link', default=None)
args = parser.parse_args()

scriptPath = os.path.dirname(os.path.abspath(__file__))

class Feeds:
    def __init__(self):
        convertors = []
        with open(os.path.join(scriptPath, "feed.input.json"), "r") as f:
            feeds = json.load(f)
            for feed in feeds:
                if feed.get("ignore", False):
                    # print(f"Ignoring {feed.get('name','')}")
                    continue
                convertor = WebToEpub(feed)
                convertors.append(convertor)
                convertor.convert()


class WebToEpub:
    def __init__(self, feedObj):
        self.completedUrls = []  # List of objects with `link` and `date`
        self.scriptPath = "~"
        self.getData()
        ssl._create_default_https_context = ssl._create_unverified_context
        self.feed = None
        if "url" in feedObj:
            self.feed = feedparser.parse(feedObj["url"])

        if "name" in feedObj:
            self.name = feedObj["name"]
        
        if "file" in feedObj:
            self.file = feedObj["file"]

    def get_last_completed_timestamp(self):
        if not self.completedUrls:
            return None
        last_completed = max(self.completedUrls, key=lambda x: x["date"])
        return last_completed["date"]

    def send_next_chapter(self):
        if not self.file:
            print("No file provided for this feed. Cannot send chapters.")
            return

        # Find the last sent chapter from `completedObjects.db`
        last_chapter = 0
        for entry in self.completedUrls:
            if entry["link"].startswith(f"chapter:{self.name}:"):
                chapter_num = int(entry["link"].split(":")[-1])
                last_chapter = max(last_chapter, chapter_num)

        next_chapter = last_chapter + 1

        # Read the EPUB file
        book = epub.read_epub(self.file)
        chapters = [item for item in book.items if isinstance(item, epub.EpubHtml)]

        if next_chapter > len(chapters):
            print(f"No more chapters to send for {self.name}.")
            return

        # Extract the next chapter
        chapter = chapters[next_chapter - 1]  # EPUB chapters are 0-indexed

        # Create a new EPUB with the single chapter
        new_book = epub.EpubBook()
        new_book.set_title(f"{self.name} - Chapter {next_chapter}")
        new_book.set_language("en")
        new_book.add_author("Unknown")
        new_book.add_item(chapter)
        new_book.spine = [chapter]

        output_file = f"/tmp/{self.name.replace(' ', '_')}_Chapter_{next_chapter}.epub"
        epub.write_epub(output_file, new_book)

        # Send the chapter using mutt
        print(f"\nSending Chapter {next_chapter}: {self.name}")
        subprocess.check_call(
            f'echo book | mutt -s "{self.name} - Chapter {next_chapter}" -a "{output_file}" -- mnishamk95@kindle.com',
            shell=True,
            cwd=self.scriptPath,
        )

        # Add the sent chapter to `completedObjects.db`
        self.completedUrls.append({
            "link": f"chapter:{self.name}:{next_chapter}",
            "date": int(time.time()),
        })
        self.saveData()

        print(f"Chapter {next_chapter} sent and added to completedObjects.db.")

    def convert(self):
        if self.file:
            last_completed = self.get_last_completed_timestamp()
            if last_completed and (int(time.time()) - last_completed) > 86400:
                self.send_next_chapter()
        if not self.feed:
            return
        for entry in self.feed.entries[::-1]:
            if not any(obj["link"] == entry.link for obj in self.completedUrls) and "Patron Early Access:" not in entry.title:
                try:
                    self.epub(entry.link, ((self.feed.feed.title + " - ") if self.feed.feed.title not in entry.title else "") + time.strftime("%Y-%m-%d", entry.published_parsed) + " - " + entry.title)
                except:
                    try:
                        args.remove_images = True
                        self.epub(entry.link, ((self.feed.feed.title + " - ") if self.feed.feed.title not in entry.title else "") + time.strftime("%Y-%m-%d", entry.published_parsed) + " - " + entry.title)
                    except Exception as e:
                        print("Exception ", str(e))

    def clean(self, url, html):
        keywordsToRemove = KEYWORDS_TO_REMOVE
        cleanedHtml = html
        if "royalroad" in url:
            cleanedHtml = cleanedHtml.find(".chapter-inner.chapter-content")[0]
            soup = BeautifulSoup(str(cleanedHtml.html), features="lxml")
            chapter_div = soup.find("div", class_="chapter-inner chapter-content")
            if not chapter_div:
                print("Could not find the chapter content div")
                return soup.prettify()
            extracted = False
            for para in chapter_div.find_all(["p", "div"]):
                if para.getText().count(".") <= 3 and para.getText().count(" ") <= 25:
                    keywordsFound = 0
                    for keyword in keywordsToRemove:
                        if keyword in para.getText().lower():
                            keywordsFound += 1
                    if keywordsFound >= 2:
                        print(f"{para.getText()} Extracted")
                        para.extract()
                        extracted = True
                        break
            if not extracted:
                print("Could not find any paragraphs")
            return soup.prettify()

        if "wanderinginn" in url:
            cleanedHtml = cleanedHtml.find("article")[0]
            cleanedHtml = cleanedHtml.find(".entry-content")[0]
            soup = BeautifulSoup(str(cleanedHtml.html), features="lxml")
            for video in soup.find_all("div", {"class": "video-player"}):
                video.extract()
            for video in soup.find_all("span", {"class": "embed-youtube"}):
                video.extract()
            if args.remove_images:
                for img in soup.find_all("img"):
                    img.extract()
                for img in soup.find_all("div", {"class": "gallery"}):
                    img.extract()
            return soup.prettify()

        return cleanedHtml.html

    def epub(self, url, title):
        title = title.replace('"', '')
        print("Downloading: ", title)
        session = HTMLSession()
        r = session.get(url)
        htmlContent = self.clean(url, r.html)
        with open("/tmp/article.html", "w") as file:
            file.write(htmlContent)
        subprocess.check_call('pandoc /tmp/article.html -o "output/' + title + '.epub" --metadata title="' + title + '" --metadata lang="en-US" --css epub.css', shell=True, cwd=self.scriptPath)
        if not args.dry_run:
            print("\nSending: ", title)
            subprocess.check_call('echo book | mutt -s "' + title + '" -a "output/' + title + '.epub" -- mnishamk95@kindle.com', shell=True, cwd=self.scriptPath)
        print("---")
        if not args.dry_run or args.update_db:
            self.complete(url)

    def complete(self, url):
        current_epoch_time = int(time.time())
        self.completedUrls.append({"link": url, "date": current_epoch_time})
        self.saveData()

    def saveData(self):
        with open(os.path.join(self.scriptPath, "completedObjects.db"), "wb") as data:
            pickle.dump(self.completedUrls, data)

    def getData(self):
        self.scriptPath = os.path.dirname(os.path.abspath(__file__))
        try:
            with open(os.path.join(self.scriptPath, "completedObjects.db"), "rb") as data:
                self.completedUrls = pickle.load(data)
        except Exception:
            with open(os.path.join(self.scriptPath, "completedObjects.db"), "wb") as data:
                pickle.dump(self.completedUrls, data)

def removeLink():
    with open(os.path.join(scriptPath, "completedObjects.db"), "rb") as data:
        completedUrls = pickle.load(data)
    updatedUrls = [obj for obj in completedUrls if obj["link"] != args.link]
    with open(os.path.join(scriptPath, "completedObjects.db"), "wb") as data:
        pickle.dump(updatedUrls, data)

def main():
    if args.link:
        if args.update_db:
            removeLink()
    else:
        Feeds()

if __name__ == "__main__":
    main()

