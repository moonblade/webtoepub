#!/usr/bin/env python3
"""
Migration script: rename /data/<rss_title> folders to /data/<feed.name>

Before this change, feeder stored files in sanitize_filename(feed.title)
where feed.title came from the RSS feed's remote title (volatile).
After the change, feeder uses sanitize_filename(feed.name) — the stable
name saved in the DB.

This script detects mismatches and renames accordingly.

Run inside the feeder pod:
    kubectl exec -it -n feeder deploy/feeder -- python3 scripts/migrate_folders_to_feed_name.py

Set DRY_RUN=true to preview without renaming.
"""

import os
import sys
import shutil
import feedparser

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_all_feeds
from feeder import sanitize_filename

DATA_PATH = os.getenv("DATA_PATH", "/data")
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"


def main():
    feeds = get_all_feeds()
    print(f"Loaded {len(feeds)} feeds from DB")
    print(f"DRY_RUN={DRY_RUN}, DATA_PATH={DATA_PATH}\n")

    renamed = 0
    skipped = 0
    already_ok = 0
    errors = 0

    for feed in feeds:
        name_folder = sanitize_filename(feed.name)
        name_path = os.path.join(DATA_PATH, name_folder)

        # Fetch the current RSS title to find the old folder name
        try:
            feed_data = feedparser.parse(feed.url)
            rss_title = feed_data.feed.get("title", "")
        except Exception as e:
            print(f"  [ERROR] {feed.name}: failed to fetch RSS: {e}")
            errors += 1
            continue

        if not rss_title:
            print(f"  [SKIP] {feed.name}: could not get RSS title")
            skipped += 1
            continue

        title_folder = sanitize_filename(rss_title)
        title_path = os.path.join(DATA_PATH, title_folder)

        if title_folder == name_folder:
            print(f"  [OK] {feed.name}: folders already match ({name_folder})")
            already_ok += 1
            continue

        # New-style folder already exists
        if os.path.isdir(name_path):
            print(f"  [OK] {feed.name}: new folder already exists ({name_folder}), old={title_folder}")
            already_ok += 1
            continue

        # Old folder exists → rename to new
        if os.path.isdir(title_path):
            print(f"  [RENAME] {feed.name}")
            print(f"    {title_folder!r}  →  {name_folder!r}")
            if not DRY_RUN:
                try:
                    shutil.move(title_path, name_path)
                    print(f"    Done.")
                    renamed += 1
                except Exception as e:
                    print(f"    [ERROR] rename failed: {e}")
                    errors += 1
            else:
                print(f"    (dry run, skipping)")
                renamed += 1
        else:
            print(f"  [MISSING] {feed.name}: neither folder exists (old={title_folder!r}, new={name_folder!r})")
            skipped += 1

    print(f"\nSummary: {renamed} renamed, {already_ok} already OK, {skipped} skipped/missing, {errors} errors")
    if DRY_RUN:
        print("(DRY RUN — no changes made)")


if __name__ == "__main__":
    main()
