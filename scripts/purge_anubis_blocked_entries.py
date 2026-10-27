#!/usr/bin/env python3
"""
Purge DB entries that were incorrectly marked as processed on Oct 26 2026.

Root cause analysis (from logs):
  - A PermissionError on the NFS /data mount starting at 08:00 on Oct 26 caused
    all chapter downloads to fail for several series.
  - Anubis also started blocking Royal Road on Oct 26 (HWFWM Ch1034, Runebound
    Ch966 — these got the Anubis challenge page, generated a tiny empty EPUB,
    and were emailed; user never received them, presumably rejected/empty).
  - The compiled-ebook path (>5 unprocessed entries) marked Primal Hunter and
    Hundred Reigns as processed despite producing 0 chapters (no email sent).
  - Legend of William Oh, Throne of Time, Archmage Coefficient hit PermissionError
    in the single-entry path — exception was caught so they were NOT marked in DB
    and will reprocess naturally once permissions are fixed.

Entries to purge from DB (confirmed by log + file inspection):
  ANUBIS html (~7-8 KB, empty epub, email sent but empty):
    - HWFWM Ch1034
    - Runebound Ch966
  NO_HTML (compiled-ebook path, marked processed, 0 chapters, no email sent):
    - Primal Hunter Ch1406-1411
    - Hundred Reigns Ch244-249

Entries NOT in DB (single-entry path, exception caught, will reprocess):
  - Legend of William Oh Ch334-337
  - Throne of Time Ch61-64
  - Archmage Coefficient Ch149-153

Usage (run AFTER new image with Anubis fix is deployed):
    # Dry run first:
    kubectl exec -n feeder deployment/feeder -- \\
        python3 - < scripts/purge_anubis_blocked_entries.py

    # Then delete:
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

# Only examine entries processed on Oct 26 or later
CUTOFF = datetime.datetime(2026, 10, 26, 0, 0, 0).timestamp()

# Real chapter HTML is always >50 KB; Anubis challenge page is ~7-8 KB
ANUBIS_HTML_MAX_BYTES = 20_000

DRY_RUN = "--delete" not in sys.argv

print(f"DB path   : {DB_PATH}")
print(f"Data path : {DATA_PATH}")
print(f"Cutoff    : 2026-10-26 00:00")
print(f"Mode      : {'DRY RUN (pass --delete to actually remove)' if DRY_RUN else '*** DELETING ***'}")
print()


def sanitize(s):
    for c in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        s = s.replace(c, '-')
    return s


def check_entry(entry) -> str | None:
    """
    Return a reason string if this entry should be purged, else None.
    Criteria:
      - time_sent >= CUTOFF
      - royalroad.com link
      - HTML file missing (PermissionError / no content) OR is Anubis challenge (<20KB)
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
        return "NO_HTML (PermissionError — compiled-ebook marked processed with 0 chapters)"

    size = os.path.getsize(html_path)
    if size < ANUBIS_HTML_MAX_BYTES:
        return f"ANUBIS challenge page ({size} bytes — empty EPUB was sent)"

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
    feed_title = entry.get("feed", {}).get("title", "")
    print(f"  [{dt}] [{reason}]")
    print(f"           {feed_title} — {title}")

print()
print("NOTE: Legend of William Oh Ch334-337, Throne of Time Ch61-64, and")
print("Archmage Coefficient Ch149-153 are NOT in the DB (single-entry path,")
print("exception was caught). They will reprocess automatically on next run.")

if not to_delete:
    print("\nNothing to delete — all recent RR entries look fine.")
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
