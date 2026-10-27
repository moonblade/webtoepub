#!/usr/bin/env python3
"""
Purge the Royal Road entries that were actually blocked by Anubis on Oct 26 2026.

Two categories confirmed by inspecting the HTML files on disk:
  1. ANUBIS   - HTML file exists but contains the Anubis challenge page (~7-8 KB).
                The EPUB was generated from that empty content and sent to Kindle.
  2. NO_HTML  - Download failed mid-run (PermissionError after directory was created
                as root). Entry is marked processed but no HTML or EPUB exists.

Only entries from Oct 26 onwards are affected. Oct 19-24 entries all have
real HTML (84-130 KB) and real EPUBs -- those are fine and must NOT be removed.

Usage:
    # Dry run (preview only, default):
    kubectl exec -n feeder deployment/feeder -- \\
        python3 - < scripts/purge_anubis_blocked_entries.py

    # Actually delete:
    kubectl exec -n feeder deployment/feeder -- \\
        python3 - --delete < scripts/purge_anubis_blocked_entries.py
"""

import json
import sys
import datetime
import shutil
import os

DB_PATH = os.path.join(os.getenv("CONFIG_PATH", "/config"), "db.json")
DATA_PATH = os.getenv("DATA_PATH", "/data")

# Only look at entries processed on Oct 26 or later (confirmed Anubis start date)
CUTOFF = datetime.datetime(2026, 10, 26, 0, 0, 0).timestamp()

# Anubis challenge page is ~7-8 KB; real chapter HTML is always >50 KB
ANUBIS_HTML_MAX_BYTES = 20_000

DRY_RUN = "--delete" not in sys.argv

print(f"DB path   : {DB_PATH}")
print(f"Data path : {DATA_PATH}")
print(f"Cutoff    : {datetime.datetime.fromtimestamp(CUTOFF).strftime('%Y-%m-%d %H:%M')} (Oct 26 2026)")
print(f"Mode      : {'DRY RUN (pass --delete to actually remove)' if DRY_RUN else '*** DELETING ***'}")
print()


def sanitize(s):
    for c in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        s = s.replace(c, '-')
    return s


def check_entry(entry) -> str | None:
    """
    Return a reason string if this entry should be purged, else None.
    Checks:
      - time_sent >= CUTOFF
      - royalroad.com link
      - HTML file missing OR is an Anubis challenge page (< ANUBIS_HTML_MAX_BYTES)
    """
    ts = entry.get("time_sent", 0)
    link = entry.get("link", "")
    if ts < CUTOFF or "royalroad.com" not in link:
        return None

    title = entry.get("title", "")
    feed = entry.get("feed", {})
    feed_title = feed.get("title", "") if isinstance(feed, dict) else ""
    if not feed_title:
        return None

    html_path = os.path.join(DATA_PATH, sanitize(feed_title), "html", sanitize(title) + ".html")

    if not os.path.exists(html_path):
        return "NO_HTML (PermissionError or never downloaded)"

    size = os.path.getsize(html_path)
    if size < ANUBIS_HTML_MAX_BYTES:
        return f"ANUBIS challenge page ({size} bytes)"

    return None  # real content, keep it


with open(DB_PATH) as f:
    db = json.load(f)

to_delete = {}  # doc_id -> (entry, reason)

for doc_id, entry in db["_default"].items():
    reason = check_entry(entry)
    if reason:
        to_delete[doc_id] = (entry, reason)

print(f"Entries to remove: {len(to_delete)}")
print()

for doc_id, (entry, reason) in sorted(to_delete.items(), key=lambda x: x[1][0].get("time_sent", 0)):
    ts = entry.get("time_sent", 0)
    dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    title = entry.get("title", "")[:65]
    print(f"  [{dt}] [{reason}]")
    print(f"           {title}")

if not to_delete:
    print("Nothing to delete — all recent RR entries look fine.")
    sys.exit(0)

print()
if DRY_RUN:
    print("Dry run complete. Re-run with --delete to remove these entries.")
    sys.exit(0)

# Backup before modifying
backup_path = DB_PATH + ".pre_purge_bak"
shutil.copy2(DB_PATH, backup_path)
print(f"Backup saved to: {backup_path}")

for doc_id in to_delete:
    del db["_default"][doc_id]

with open(DB_PATH, "w") as f:
    json.dump(db, f)

print(f"Deleted {len(to_delete)} entries from {DB_PATH}")
print("Feeder will reprocess and resend these chapters on the next cron run.")
