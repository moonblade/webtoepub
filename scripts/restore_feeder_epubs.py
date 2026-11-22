#!/usr/bin/env python3
"""
Restore feeder EPUBs from Calibre library back to /mnt/nas/feeder/<feed_name>/ folders.

The Calibre library at BOOKS_PATH contains EPUBs that were originally generated
by feeder and ingested by calibre-web-automated. This script reads dc:subject
(= feed/series name) from each EPUB's OPF, then copies the EPUB to the correct
feeder folder.

Mapping:
  BOOKS_PATH/<chapter_title>/<calibre_folder>/<file>.epub
    → FEEDER_PATH/<dc:subject>/<dc:title>.epub

Run:
  DRY_RUN=true python3 scripts/restore_feeder_epubs.py   # preview
  python3 scripts/restore_feeder_epubs.py                # apply

Env vars:
  BOOKS_PATH   default /mnt/nas/books
  FEEDER_PATH  default /mnt/nas/feeder
  DRY_RUN      default false
"""

import os
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

BOOKS_PATH = os.getenv("BOOKS_PATH", "/mnt/nas/books")
FEEDER_PATH = os.getenv("FEEDER_PATH", "/mnt/nas/feeder")
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# Feed series names → feeder folder names (dc:subject values we know about)
# These are the exact dc:subject values written by feeder
KNOWN_FEEDS = {
    "12 Miles Below",
    "All The Skills - A Deckbuilding LitRPG",
    "A Practical Guide to Sorcery",
    "Ar'Kendrithyst",
    "Beware Of Chicken",
    "Bog Standard Isekai",
    "Book Of The Dead",
    "Chrysalis",
    "He Who Fights With Monsters",
    "Heretical Fishing: A Cozy Guide to Annoying the Cults, Outsmarting the Fish, and Alienating Oneself",
    "Magic is Programming",
    "Mark of the Fool",
    "Nightmare Realm Summoner",
    "Paranoid Mage",
    "Re:Birth: A LitRPG Mage Regressor",
    "Return of the Runebound Professor",
    "Rise of the Living Forge",
    "Super Supportive",
    "TeeKay",
    "The 108",
    "The Archmage Coefficient (OP Archmage- Mage Academy- LITRPG- Hidden Genius)",
    "The Archmage's Second Life as an Introvert",
    "The Greatest Archmage To Have Ever Lived",
    "The Hundred Reigns",
    "The Legend of William Oh",
    "The Path of Ascension",
    "The Perfect Run",
    "The Primal Hunter",
    "The Stubborn Skill-Grinder In A Time Loop",
    "The Stubborn Skill-Grinder In A Time Loop (Book 1 Stubbed For Amazon)",
    "The Stubborn Skill-Grinder In A Time Loop (Book 2 Stubbed)",
    "The Stubborn Skill-Grinder In A Time Loop (Book 3 Stubbed)",
    "The Stubborn Skill-Grinder In A Time Loop (Book 4 Stubbed)",
    "The Stubborn Skill-Grinder In A Time Loop (Book 5 Stubbed)",
    "The Stubborn Skill-Grinder In A Time Loop (Stubbing In A Month)",
    "The Stubborn Skill-Grinder In A Time Loop (Stubbing In One Week)",
    "The Stubborn Skill-Grinder In A Time Loop (Stubbing In Three Days)",
    "The Stubborn Skill-Grinder In A Time Loop (Stubbing In Three Weeks)",
    "The Stubborn Skill-Grinder In A Time Loop (Stubbing In Two Weeks)",
    "The Wandering Inn",
    "The Years of Apocalypse",
    "Zenith of Sorcery",
}


def sanitize_filename(filename: str) -> str:
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in invalid_chars:
        filename = filename.replace(char, '-')
    return filename


def read_opf_metadata(epub_path: str):
    """Extract dc:title, dc:subject from EPUB OPF. Returns (title, subject) or (None, None)."""
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            # Find OPF file
            opf_files = [f for f in z.namelist() if f.endswith('.opf')]
            if not opf_files:
                return None, None
            content = z.read(opf_files[0]).decode('utf-8', errors='replace')

        # Parse title
        title_m = re.search(r'<dc:title[^>]*>([^<]+)</dc:title>', content)
        title = title_m.group(1).strip() if title_m else None

        # Parse subject (dc:subject = feed/series name set by feeder)
        subject_m = re.search(r'<dc:subject[^>]*>([^<]+)</dc:subject>', content)
        subject = subject_m.group(1).strip() if subject_m else None

        # Unescape HTML entities (including numeric &#39; → ')
        def unescape(s):
            import html
            return html.unescape(s) if s else s
        subject = unescape(subject)
        title = unescape(title)

        return title, subject

    except Exception as e:
        return None, None


def main():
    print(f"BOOKS_PATH={BOOKS_PATH}")
    print(f"FEEDER_PATH={FEEDER_PATH}")
    print(f"DRY_RUN={DRY_RUN}\n")

    stats = {"copied": 0, "skipped_exists": 0, "skipped_no_subject": 0, "skipped_unknown_feed": 0, "errors": 0}
    unknown_subjects = set()

    epub_files = list(Path(BOOKS_PATH).rglob("*.epub"))
    print(f"Found {len(epub_files)} EPUBs in {BOOKS_PATH}\n")

    for epub_path in sorted(epub_files):
        epub_str = str(epub_path)

        title, subject = read_opf_metadata(epub_str)

        if not subject:
            stats["skipped_no_subject"] += 1
            continue

        # Check if subject matches a known feeder feed
        # Try exact match first, then sanitized match, then prefix match
        feed_folder = None
        if subject in KNOWN_FEEDS:
            feed_folder = subject
        else:
            san_subject = sanitize_filename(subject)
            for known in KNOWN_FEEDS:
                if san_subject == sanitize_filename(known) or subject.startswith(known):
                    feed_folder = known
                    break
            # Also try: known feed name (sanitized) matches sanitized subject prefix
            if not feed_folder:
                for known in KNOWN_FEEDS:
                    if sanitize_filename(known) == san_subject:
                        feed_folder = known
                        break

        if not feed_folder:
            unknown_subjects.add(subject)
            stats["skipped_unknown_feed"] += 1
            continue

        # Determine destination filename from dc:title
        if title:
            dest_filename = sanitize_filename(title) + ".epub"
        else:
            dest_filename = epub_path.name

        dest_dir = os.path.join(FEEDER_PATH, feed_folder)
        dest_path = os.path.join(dest_dir, dest_filename)

        if os.path.exists(dest_path):
            stats["skipped_exists"] += 1
            continue

        print(f"COPY: {subject!r}")
        print(f"      {epub_str}")
        print(f"   → {dest_path}")

        if not DRY_RUN:
            try:
                os.makedirs(dest_dir, exist_ok=True)
                shutil.copy2(epub_str, dest_path)
                stats["copied"] += 1
            except Exception as e:
                print(f"  ERROR: {e}")
                stats["errors"] += 1
        else:
            stats["copied"] += 1

    print(f"\n--- Summary ---")
    print(f"Copied:                {stats['copied']}")
    print(f"Skipped (exists):      {stats['skipped_exists']}")
    print(f"Skipped (no subject):  {stats['skipped_no_subject']}")
    print(f"Skipped (unknown feed):{stats['skipped_unknown_feed']}")
    print(f"Errors:                {stats['errors']}")

    if unknown_subjects:
        print(f"\nUnknown subjects (not matched to any feeder feed):")
        for s in sorted(unknown_subjects):
            print(f"  {s!r}")

    if DRY_RUN:
        print("\n(DRY RUN — no files were copied)")


if __name__ == "__main__":
    main()
