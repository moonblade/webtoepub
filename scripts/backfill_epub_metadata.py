#!/usr/bin/env python3
"""
Backfill Calibre-compatible metadata into all existing per-chapter EPUB files.

What it does:
  - Iterates every <feed_title>/<chapter>.epub in DATA_PATH
  - Skips compiled _compiled.epub files (those are re-generated differently)
  - For each chapter EPUB, checks if the corresponding cleaned HTML exists
  - If yes: deletes the old EPUB and re-runs convert_to_epub() with the new
    metadata (calibre:series, calibre:series_index, author, dc:subject)
  - Derives series_index from the chapter title via _extract_chapter_number()

Run inside the container or with the same venv as feeder.py:
  python3 scripts/backfill_epub_metadata.py

Environment variables (same as feeder.py):
  DATA_PATH   — default /data
  DEBUG_MODE  — set to "true" for a dry run (no deletes/conversions)
"""

import os
import sys
import re

# Add parent dir to path so we can import feeder modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feeder import (
    _extract_chapter_number,
    _build_epub_metadata_xml,
    sanitize_filename,
)
from db import get_all_feeds
from models import FeedItem
from utils import custom_logger
import pypandoc
import tempfile

logger = custom_logger("backfill_epub_metadata")

DATA_PATH = os.getenv("DATA_PATH", "/data")
DRY_RUN = os.getenv("DEBUG_MODE", "false").lower() == "true"


def get_feed_map() -> dict[str, FeedItem]:
    """
    Returns a dict of {sanitized_folder_name: FeedItem} from the DB.
    We match by sanitized title since that's how folders are named.
    """
    feeds = get_all_feeds()
    result = {}
    for f in feeds:
        item = FeedItem(**f) if isinstance(f, dict) else f
        # Reproduce the same title stripping feeder does
        title = re.sub(r"\[.*?\]", "", item.title or item.name).strip()
        result[sanitize_filename(title)] = item
    return result


def rewrite_epub(epub_path: str, cleaned_html_path: str, title: str, author: str, series: str, series_index=None):
    """
    Delete existing EPUB and regenerate it from cleaned HTML with new metadata.
    """
    logger.info(f"  Rewriting: {os.path.basename(epub_path)}")
    if DRY_RUN:
        logger.info(f"  [DRY RUN] Would rewrite {epub_path}")
        return True

    metadata_xml = _build_epub_metadata_xml(
        title=title,
        author=author,
        series=series,
        series_index=series_index,
    )

    tmp_epub = epub_path + ".tmp.epub"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as mf:
        mf.write(metadata_xml)
        metadata_file_path = mf.name

    try:
        # epub.css lives next to feeder.py (parent dir of scripts/, or /app in container)
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        css_path = os.path.join(script_dir, 'epub.css')
        if not os.path.exists(css_path):
            css_path = os.path.join(os.getcwd(), 'epub.css')
        extra_args = [
            '--epub-metadata', metadata_file_path,
            '--metadata', 'lang=en-US',
            '--css', css_path,
            '--epub-title-page=false',
        ]
        pypandoc.convert_file(
            cleaned_html_path,
            'epub',
            outputfile=tmp_epub,
            extra_args=extra_args,
        )
    finally:
        os.unlink(metadata_file_path)

    os.replace(tmp_epub, epub_path)
    return True


def main():
    logger.info(f"Starting EPUB metadata backfill (DATA_PATH={DATA_PATH}, DRY_RUN={DRY_RUN})")

    feed_map = get_feed_map()
    logger.info(f"Loaded {len(feed_map)} feeds from DB: {list(feed_map.keys())}")

    total = 0
    skipped = 0
    rewritten = 0
    errors = 0

    for folder_name in sorted(os.listdir(DATA_PATH)):
        folder_path = os.path.join(DATA_PATH, folder_name)
        if not os.path.isdir(folder_path):
            continue

        feed_item = feed_map.get(folder_name)
        if feed_item is None:
            logger.warning(f"No feed found for folder '{folder_name}' — skipping")
            continue

        # Reconstruct series title the same way feeder does
        series = re.sub(r"\[.*?\]", "", feed_item.title or feed_item.name).strip()
        author = feed_item.author if feed_item.author else series

        logger.info(f"\nProcessing feed: {series} ({folder_name})")
        cleaned_dir = os.path.join(folder_path, "cleaned")

        epub_files = [
            f for f in os.listdir(folder_path)
            if f.endswith('.epub') and not f.endswith('_compiled.epub')
        ]
        logger.info(f"  Found {len(epub_files)} chapter EPUBs")

        for epub_filename in sorted(epub_files):
            total += 1
            epub_path = os.path.join(folder_path, epub_filename)

            # Derive chapter title from filename (reverse of sanitize_filename)
            # The filename IS the sanitized title + .epub
            chapter_title = epub_filename[:-5]  # strip .epub
            # Replace sanitized chars back — only underscores from spaces
            # (other chars were replaced with - and we can't reverse that, but title is used for display)
            chapter_display_title = chapter_title.replace('_', ' ')

            # Find corresponding cleaned HTML
            cleaned_html = os.path.join(cleaned_dir, f"{chapter_title}.html")
            if not os.path.exists(cleaned_html):
                logger.warning(f"  No cleaned HTML for {epub_filename} — skipping")
                skipped += 1
                continue

            series_index = _extract_chapter_number(chapter_display_title)

            try:
                rewrite_epub(
                    epub_path=epub_path,
                    cleaned_html_path=cleaned_html,
                    title=chapter_display_title,
                    author=author,
                    series=series,
                    series_index=series_index,
                )
                rewritten += 1
            except Exception as e:
                logger.error(f"  ERROR rewriting {epub_filename}: {e}")
                errors += 1

    logger.info(f"\n=== Backfill complete ===")
    logger.info(f"  Total:    {total}")
    logger.info(f"  Rewritten:{rewritten}")
    logger.info(f"  Skipped:  {skipped}")
    logger.info(f"  Errors:   {errors}")


if __name__ == "__main__":
    main()
