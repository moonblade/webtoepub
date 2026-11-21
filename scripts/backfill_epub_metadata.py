#!/usr/bin/env python3
"""
Backfill Calibre-compatible metadata into all existing per-chapter EPUB files.

What it does:
  - Iterates every <feed_title>/<chapter>.epub in DATA_PATH
  - Skips compiled _compiled.epub files (those are re-generated differently)
  - For each chapter EPUB, checks if the corresponding cleaned HTML exists
  - If yes: rewrites the EPUB via pandoc with calibre:series/series_index/author metadata
  - Derives series_index from the chapter title via _extract_chapter_number()

Checkpoint / resume support:
  - A checkpoint file (CHECKPOINT_PATH, default /tmp/backfill_checkpoint.json) records
    every successfully rewritten EPUB path.
  - On re-run, already-checkpointed files are skipped instantly.
  - Delete the checkpoint file to force a full re-run from scratch.

Run inside the container or with the same venv as feeder.py:
  cd /app && python3 backfill_epub_metadata.py

Environment variables:
  DATA_PATH        — default /data
  DEBUG_MODE       — set to "true" for a dry run (no writes, no checkpoint updates)
  CHECKPOINT_PATH  — default /tmp/backfill_checkpoint.json
"""

import json
import os
import re
import sys
import tempfile

# Add parent dir to path so we can import feeder modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feeder import (
    _build_epub_metadata_xml,
    _extract_chapter_number,
    sanitize_filename,
)
from db import get_all_feeds
from models import FeedItem
from utils import custom_logger
import pypandoc

logger = custom_logger("backfill_epub_metadata")

DATA_PATH = os.getenv("DATA_PATH", "/data")
DRY_RUN = os.getenv("DEBUG_MODE", "false").lower() == "true"
CHECKPOINT_PATH = os.getenv("CHECKPOINT_PATH", "/tmp/backfill_checkpoint.json")


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def load_checkpoint() -> set:
    """Load the set of already-completed epub paths from the checkpoint file."""
    if os.path.exists(CHECKPOINT_PATH):
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            done = set(data.get("done", []))
            logger.info(f"Checkpoint loaded: {len(done)} already-done files from {CHECKPOINT_PATH}")
            return done
        except Exception as e:
            logger.warning(f"Could not read checkpoint ({e}); starting fresh")
    return set()


def save_checkpoint(done: set):
    """Persist the checkpoint atomically."""
    if DRY_RUN:
        return
    tmp = CHECKPOINT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"done": sorted(done)}, f)
    os.replace(tmp, CHECKPOINT_PATH)


# ---------------------------------------------------------------------------
# Feed helpers
# ---------------------------------------------------------------------------

def get_feed_map() -> dict:
    """Return {sanitized_folder_name: FeedItem} from the DB."""
    feeds = get_all_feeds()
    result = {}
    for f in feeds:
        item = FeedItem(**f) if isinstance(f, dict) else f
        title = re.sub(r"\[.*?\]", "", item.title or item.name).strip()
        result[sanitize_filename(title)] = item
    return result


# ---------------------------------------------------------------------------
# EPUB rewrite
# ---------------------------------------------------------------------------

def rewrite_epub(epub_path: str, cleaned_html_path: str, title: str,
                 author: str, series: str, series_index=None) -> bool:
    """Rewrite an EPUB in-place with Calibre-compatible OPF metadata."""
    if DRY_RUN:
        logger.info(f"  [DRY RUN] Would rewrite: {os.path.basename(epub_path)}")
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
        # epub.css lives next to feeder.py (parent dir of scripts/, or cwd in container)
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info(
        f"Starting EPUB metadata backfill "
        f"(DATA_PATH={DATA_PATH}, DRY_RUN={DRY_RUN}, CHECKPOINT={CHECKPOINT_PATH})"
    )

    done = load_checkpoint()
    feed_map = get_feed_map()
    logger.info(f"Loaded {len(feed_map)} feeds from DB")

    total = skipped_checkpoint = skipped_no_html = rewritten = errors = 0

    for folder_name in sorted(os.listdir(DATA_PATH)):
        folder_path = os.path.join(DATA_PATH, folder_name)
        if not os.path.isdir(folder_path):
            continue

        feed_item = feed_map.get(folder_name)
        if feed_item is None:
            logger.warning(f"No feed found for folder '{folder_name}' — skipping")
            continue

        series = re.sub(r"\[.*?\]", "", feed_item.title or feed_item.name).strip()
        author = feed_item.author if feed_item.author else series

        logger.info(f"\nProcessing feed: {series}")
        cleaned_dir = os.path.join(folder_path, "cleaned")

        epub_files = [
            f for f in os.listdir(folder_path)
            if f.endswith('.epub') and not f.endswith('_compiled.epub')
        ]
        logger.info(f"  Found {len(epub_files)} chapter EPUBs")

        for epub_filename in sorted(epub_files):
            total += 1
            epub_path = os.path.join(folder_path, epub_filename)

            # Resume: skip if already done in a previous run
            if epub_path in done:
                skipped_checkpoint += 1
                continue

            chapter_title = epub_filename[:-5]  # strip .epub
            chapter_display_title = chapter_title.replace('_', ' ')

            cleaned_html = os.path.join(cleaned_dir, f"{chapter_title}.html")
            if not os.path.exists(cleaned_html):
                logger.warning(f"  No cleaned HTML for {epub_filename} — skipping")
                skipped_no_html += 1
                continue

            series_index = _extract_chapter_number(chapter_display_title)
            logger.info(f"  Rewriting: {epub_filename}")

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
                done.add(epub_path)
                # Flush checkpoint after every successful write so crashes are resumable
                save_checkpoint(done)
            except Exception as e:
                logger.error(f"  ERROR rewriting {epub_filename}: {e}")
                errors += 1

    logger.info(f"\n=== Backfill complete ===")
    logger.info(f"  Total found:        {total}")
    logger.info(f"  Rewritten:          {rewritten}")
    logger.info(f"  Skipped (checkpoint):{skipped_checkpoint}")
    logger.info(f"  Skipped (no HTML):  {skipped_no_html}")
    logger.info(f"  Errors:             {errors}")
    logger.info(f"  Checkpoint:         {CHECKPOINT_PATH}")


if __name__ == "__main__":
    main()
