#!/usr/bin/env python3
"""
Purge Royal Road entries that were marked as processed while Anubis was
blocking downloads (approx Oct 17 2026 onwards).

Those entries have time_sent set but the downloaded HTML was actually the
Anubis challenge page, so the EPUBs delivered to Kindle were empty/broken.
Removing them from the DB causes feeder to reprocess and resend them
correctly once the new image (with the Anubis solver) is running.

Usage:
    # Dry run (preview only):
    python3 scripts/purge_anubis_blocked_entries.py

    # Actually delete:
    python3 scripts/purge_anubis_blocked_entries.py --delete

    # Run inside the cluster pod:
    kubectl exec -n feeder deployment/feeder -- python3 - < scripts/purge_anubis_blocked_entries.py
    kubectl exec -n feeder deployment/feeder -- python3 - --delete < scripts/purge_anubis_blocked_entries.py
"""

import json
import sys
import datetime
import shutil
import os

DB_PATH = os.getenv("CONFIG_PATH", "/config") + "/db.json"

# Entries processed on/after this date are candidates for deletion.
# Oct 17 is when Anubis started blocking Royal Road (based on last good entry Oct 16).
CUTOFF = datetime.datetime(2026, 10, 17, 0, 0, 0).timestamp()

DRY_RUN = "--delete" not in sys.argv

print(f"DB path   : {DB_PATH}")
print(f"Cutoff    : {datetime.datetime.fromtimestamp(CUTOFF).strftime('%Y-%m-%d %H:%M')}")
print(f"Mode      : {'DRY RUN (pass --delete to actually remove)' if DRY_RUN else '*** DELETING ***'}")
print()

with open(DB_PATH) as f:
    db = json.load(f)

entries = db["_default"]
to_delete = {}

for doc_id, entry in entries.items():
    ts = entry.get("time_sent", 0)
    link = entry.get("link", "")
    if ts > CUTOFF and "royalroad.com" in link:
        to_delete[doc_id] = entry

print(f"Entries to remove: {len(to_delete)}")
print()

for doc_id, entry in sorted(to_delete.items(), key=lambda x: x[1].get("time_sent", 0)):
    ts = entry.get("time_sent", 0)
    dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    title = entry.get("title", "unknown")[:70]
    link = entry.get("link", "")
    print(f"  [{dt}] {title}")
    print(f"           {link}")

if not to_delete:
    print("Nothing to delete.")
    sys.exit(0)

if DRY_RUN:
    print()
    print("Dry run complete. Re-run with --delete to remove these entries.")
    sys.exit(0)

# Backup before modifying
backup_path = DB_PATH + ".pre_purge_bak"
shutil.copy2(DB_PATH, backup_path)
print(f"\nBackup saved to: {backup_path}")

for doc_id in to_delete:
    del db["_default"][doc_id]

with open(DB_PATH, "w") as f:
    json.dump(db, f)

print(f"Deleted {len(to_delete)} entries from {DB_PATH}")
print("Feeder will reprocess and resend these chapters on the next run.")
