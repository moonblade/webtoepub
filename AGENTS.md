# PROJECT KNOWLEDGE BASE

**Generated:** 2026-02-21
**Commit:** e112996
**Branch:** main

## OVERVIEW

Automated web novel to EPUB converter. Monitors RSS feeds (Royal Road, Wandering Inn), converts chapters to EPUB, emails to Kindle. FastAPI web UI for history/revert.

## STRUCTURE

```
webtoepub/
├── main.py           # FastAPI server, endpoints, periodic task runner
├── feeder.py         # Core processing: download → clean → convert → email
├── webtoepub.py      # Legacy CLI script (still functional, uses mutt)
├── db.py             # TinyDB operations
├── models.py         # Pydantic models: Entry, Feed, FeedItem, EntryType
├── mail.py           # Gmail SMTP sender
├── utils.py          # Logger, sanitize_filename, delete_entry_files
├── templates/        # Jinja2 templates
│   └── index.html    # Dark-themed sent items UI with revert
├── secrets/          # Git-encrypted credentials (mailconfig.json)
├── epub.css          # EPUB styling
├── keywords.txt      # Royal Road watermark detection keywords
└── feed.input.json   # Local feed config fallback
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add site cleaner | `feeder.py` `clean_*()` | Follow `clean_wandering_inn` pattern |
| Modify entry detection | `feeder.py` `has_entry()`, `db.py` | Patreon lock logic in both |
| Change email format | `mail.py` `send_gmail()` | Uses MIME multipart |
| Add API endpoint | `main.py` | FastAPI routes, Jinja2 for HTML |
| Modify EPUB metadata | `feeder.py` `convert_to_epub()` | pypandoc extra_args |
| Change batch behavior | `feeder.py` | `MAX_BATCH_SIZE`, `ENTRY_THRESHOLD_FOR_NEW_BOOK` |
| Add new entry type | `models.py` `EntryType` | Then add cleaner in feeder.py |

## DATA FLOW

```
execute() → get_feed_list() → process_feed() → process_feed_item()
    ↓
For each entry:
    download() → clean() → convert_to_epub() → prepare_email()
    ↓
send_batch_emails() → add_entry() to TinyDB
```

## KEY PATTERNS

### Site-Specific Cleaners
```python
# In feeder.py - pattern for adding new site support:
def clean_SITENAME(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "lxml")
    # 1. Find content container
    # 2. Remove unwanted elements (ads, videos, images)
    # 3. Return prettified HTML
    return content.prettify()

# Then add to clean():
if "SITENAME" in entry.link:
    cleaned_html = clean_SITENAME(html_content)
```

### Entry Type Flow
1. Add to `EntryType` enum in `models.py`
2. Detect in `process_entry()` via URL fragment
3. Create cleaner function `clean_sitename()`
4. Add conditional in `clean()`

### Compiled Ebook Detection
When `unprocessed_entries > ENTRY_THRESHOLD_FOR_NEW_BOOK`:
- Royal Road: Scrapes TOC for all chapters
- Creates single compiled EPUB with TOC
- Marks all entries as processed

## ENVIRONMENT VARIABLES

| Variable | Default | Purpose |
|----------|---------|---------|
| `DOWNLOAD_PATH` | `/feeds` | Storage for HTML, cleaned, EPUB, db.json |
| `DEBUG_MODE` | `false` | Limits to 2 feeds, sets dry_run |
| `MAX_BATCH_SIZE` | `20` | Fails batch if exceeded |
| `ENTRY_THRESHOLD_FOR_NEW_BOOK` | `5` | Triggers compiled ebook creation |
| `PATREON_LOCK_HOURS` | `4` | Hours to ignore patreon-locked content |

## ANTI-PATTERNS

- **NEVER** hardcode email addresses - use env vars
- **NEVER** commit `secrets/mailconfig.json` - git-encrypted
- **NEVER** send emails without checking `has_entry()` first
- **NEVER** exceed `MAX_BATCH_SIZE` - batch will fail entirely
- **AVOID** modifying `webtoepub.py` - legacy, uses different DB (pickle)

## DATABASE

TinyDB at `$DOWNLOAD_PATH/db.json`. Entry keyed by `link`.

**Patreon lock logic**: Entry ignored if `patreon_lock > current_time`. Set via `set_patreon_lock()` to `now + PATREON_LOCK_HOURS`.

**Query pattern in `has_entry()`**:
```python
(Entry.link == entry.link) & 
((Entry.time_sent != 0) | 
 ((Entry.time_sent == 0) & (Entry.patreon_lock > current_time)))
```

## FILE ORGANIZATION

Per-feed structure under `$DOWNLOAD_PATH`:
```
{feed_title}/
├── html/          # Raw downloaded HTML
├── cleaned/       # Processed HTML (ads removed)
└── *.epub         # Final EPUB files
```

## COMMANDS

```bash
# Development
make venv           # Create virtual environment
make requirements   # Install dependencies
make run            # Start FastAPI server (port 9000)
make feeder         # Run feed processor once

# Docker
make build          # Build Docker image
docker-compose up   # Run with compose
```

## GIT WORKFLOW

- **PRs**: Always create a new branch from `main` for all changes, then open PR
- **Branch naming**: Use descriptive names like `remove-feedurl`, `add-site-cleaner`
- **Commits**: Keep atomic, use lowercase imperative style

## GOTCHAS

1. **Two DB systems**: `feeder.py` uses TinyDB (`db.json`), legacy `webtoepub.py` uses pickle (`completedObjects.db`)
2. **Title sanitization**: `sanitize_filename()` exists in both `feeder.py` and `utils.py` - use utils version
3. **Feed fallback**: If DB empty after migration, falls back to `feed.input.json`
4. **Compiled books**: All entries marked processed even if email fails
5. **Royal Road TOC scrape**: Requires `<table id="chapters">` - breaks if RR changes layout
