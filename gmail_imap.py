"""
Gmail IMAP module for scanning sent emails as source of truth.

Connects to Gmail via IMAP and scans the [Gmail]/Sent Mail folder to find
previously sent epub emails.

Two indexes are built from every scan:

  1. URL index  (primary, new-style subjects):
       Subject: {feed_title} - {entry_title} | {entry_url}
       Maps  url -> sent_timestamp

  2. Title index (secondary/legacy, old-style subjects):
       Subject: {feed_title} - {entry_title}
       Maps  normalised_title -> sent_timestamp
       Used as a fallback when the URL is not in the subject.
       Can be removed once all legacy emails have aged out of the inbox.

The title index normalises subjects by stripping the leading "{feed_title} - "
prefix and lowercasing before storing, so look-ups are case-insensitive.
"""
import imaplib
import email
import email.header
import email.utils
import os
import re
import time
from typing import Optional
from utils import custom_logger

logger = custom_logger(__name__)

SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))

# Folder name for Gmail sent mail — IMAP name varies by locale
GMAIL_SENT_FOLDER = "[Gmail]/Sent Mail"
GMAIL_SENT_FOLDER_ALTERNATIVES = ["Sent", "Sent Items", "INBOX.Sent"]

# Regex to extract URL from the new-style subject
# Subject: Feed Title - Chapter Title | https://example.com/chapter/123
URL_IN_SUBJECT_RE = re.compile(r'\|\s*(https?://\S+)\s*$')

# Cache TTL (seconds). Default: 15 minutes.
CACHE_TTL = int(os.getenv("IMAP_CACHE_TTL", str(15 * 60)))

# Cache state
_cache: Optional[dict] = None   # {"url": {url: ts}, "title": {norm_title: ts}}
_cache_loaded_at: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _connect() -> imaplib.IMAP4_SSL:
    """Open and authenticate an IMAP SSL connection."""
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(SENDER_EMAIL, APP_PASSWORD)
    return mail


def _parse_date(date_str: str) -> int:
    """Convert an RFC 2822 Date header to a Unix timestamp."""
    try:
        return int(email.utils.parsedate_to_datetime(date_str).timestamp())
    except Exception:
        return int(time.time())


def _decode_subject(raw: str) -> str:
    """Decode a potentially RFC 2047-encoded Subject header."""
    parts = email.header.decode_header(raw)
    out = ""
    for part, charset in parts:
        if isinstance(part, bytes):
            out += part.decode(charset or "utf-8", errors="replace")
        else:
            out += part
    return out


# Matches a date prefix at the start: "2024-01-01 - rest" -> "rest"
_DATE_PREFIX_RE = re.compile(r'^\d{4}-\d{2}-\d{2} - ')
# Matches a date infix in the middle: "feed - 2024-01-01 - chapter" -> "feed - chapter"
_DATE_INFIX_RE = re.compile(r' - \d{4}-\d{2}-\d{2} - ')
# Matches a date suffix in parens at the end: "title(2024-01-01)" -> "title"
_DATE_SUFFIX_RE = re.compile(r'\(\d{4}-\d{2}-\d{2}\)\s*$')


def _normalise_title(subject: str) -> str:
    """
    Collapse MIME folding whitespace, strip URL suffix, and lower-case.
    """
    # Collapse MIME folded lines (\r\n + whitespace) into a single space
    subject = re.sub(r'\r?\n\s+', ' ', subject)
    # Remove URL suffix if present
    subject = URL_IN_SUBJECT_RE.sub("", subject).strip()
    return subject.lower()


def _date_variants(normalised_subject: str) -> list:
    """
    Return all date-stripped variants of a normalised subject so the title
    index can match entry.title regardless of where the date was embedded.

    Observed formats in the wild:
      "2024-01-01 - feed name - chapter x"   (date prefix  — old feeder style)
      "feed name - 2024-01-01 - chapter x"   (date infix   — newer feeder style)
      "feed name - chapter x(2024-01-01)"    (date suffix in parens)
    """
    variants = []

    # Strip date prefix -> "feed name - chapter x"
    no_prefix = _DATE_PREFIX_RE.sub('', normalised_subject, count=1)
    if no_prefix != normalised_subject:
        variants.append(no_prefix)

    # Strip date infix -> "feed name - chapter x"
    no_infix = _DATE_INFIX_RE.sub(' - ', normalised_subject, count=1)
    if no_infix != normalised_subject:
        variants.append(no_infix)

    # Strip date suffix in parens
    no_suffix = _DATE_SUFFIX_RE.sub('', normalised_subject).strip()
    if no_suffix != normalised_subject:
        variants.append(no_suffix)

    return variants


# ---------------------------------------------------------------------------
# Core scan
# ---------------------------------------------------------------------------

def _select_sent_folder(mail: imaplib.IMAP4_SSL):
    """Select the Sent Mail folder; tries several common names."""
    for folder in [GMAIL_SENT_FOLDER] + GMAIL_SENT_FOLDER_ALTERNATIVES:
        status, _ = mail.select(f'"{folder}"', readonly=True)
        if status == "OK":
            return True
    return False


def _scan_imap() -> dict:
    """
    Connect to IMAP and build both indexes.

    Returns:
        {
          "url":   {url_str: timestamp_int, ...},
          "title": {norm_title_str: timestamp_int, ...},
        }
    """
    url_index: dict = {}
    title_index: dict = {}

    mail = _connect()
    try:
        if not _select_sent_folder(mail):
            logger.error("Could not select any Sent Mail folder via IMAP.")
            return {"url": {}, "title": {}}

        status, data = mail.search(None, "ALL")
        if status != "OK":
            logger.error("IMAP SEARCH ALL failed.")
            return {"url": {}, "title": {}}

        message_ids = data[0].split()
        if not message_ids:
            return {"url": {}, "title": {}}

        logger.info(f"Scanning {len(message_ids)} sent emails for epub tracking...")

        batch_size = 100
        for i in range(0, len(message_ids), batch_size):
            batch = message_ids[i: i + batch_size]
            id_str = b",".join(batch).decode()
            status, msg_data = mail.fetch(id_str, "(RFC822.HEADER)")
            if status != "OK":
                continue

            for item in msg_data:
                if not isinstance(item, tuple):
                    continue
                try:
                    msg = email.message_from_bytes(item[1])
                    subject = _decode_subject(msg.get("Subject", ""))
                    ts = _parse_date(msg.get("Date", ""))

                    # --- Primary: URL index ---
                    url_match = URL_IN_SUBJECT_RE.search(subject)
                    if url_match:
                        url = url_match.group(1).strip()
                        if url not in url_index or ts < url_index[url]:
                            url_index[url] = ts

                    # --- Secondary: title index ---
                    # Store the normalised subject plus all date-stripped
                    # variants so has_entry() can match regardless of where
                    # the date appeared in the original subject.
                    norm = _normalise_title(subject)
                    if norm and (norm not in title_index or ts < title_index[norm]):
                        title_index[norm] = ts
                    for variant in _date_variants(norm):
                        if variant not in title_index or ts < title_index[variant]:
                            title_index[variant] = ts

                except Exception as e:
                    logger.debug(f"Error parsing email header: {e}")

    finally:
        try:
            mail.logout()
        except Exception:
            pass

    logger.info(
        f"IMAP scan complete: {len(url_index)} URL matches, "
        f"{len(title_index)} title entries indexed."
    )
    return {"url": url_index, "title": title_index}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_sent_indexes(force_refresh: bool = False) -> dict:
    """
    Return the dual-index cache, refreshing from IMAP if stale.

    Structure:
        {
          "url":   {url: timestamp},
          "title": {normalised_subject: timestamp},
        }
    """
    global _cache, _cache_loaded_at

    now = int(time.time())
    if (
        not force_refresh
        and _cache is not None
        and (now - _cache_loaded_at) < CACHE_TTL
    ):
        return _cache

    if not SENDER_EMAIL or not APP_PASSWORD:
        logger.warning(
            "IMAP credentials not configured (SENDER_EMAIL / APP_PASSWORD). "
            "Skipping sent-mail scan."
        )
        _cache = {"url": {}, "title": {}}
        _cache_loaded_at = now
        return _cache

    try:
        result = _scan_imap()
    except Exception as e:
        logger.exception(f"IMAP scan failed: {e}")
        # Keep stale cache rather than wiping it
        if _cache is not None:
            return _cache
        result = {"url": {}, "title": {}}

    _cache = result
    _cache_loaded_at = now
    return _cache


def has_been_sent_via_email(url: str, entry_title: str = "") -> bool:
    """
    Return True if the entry has been sent before, using either the URL
    (new-style subjects) or the entry title (legacy subjects).

    Args:
        url:         The canonical chapter/entry URL.
        entry_title: The full entry title as it appears in the email subject
                     (e.g. "2024-01-01 - Chapter 5"). Used as legacy fallback.
    """
    indexes = fetch_sent_indexes()

    # Primary check: URL in subject
    if url in indexes["url"]:
        return True

    # Secondary check: title match (legacy emails without URL in subject).
    # LEGACY FALLBACK — expires 2026-12-02. Remove this block after that date.
    if entry_title and time.time() < 1796169600:  # 2026-12-02 00:00:00 UTC
        norm = entry_title.lower().strip()
        for indexed_subject in indexes["title"]:
            # The indexed subject is the full "feed - title" string; the entry
            # title appears as the suffix after the first " - " separator.
            # We check whether the normalised entry title is a suffix of any
            # indexed subject to avoid feed-name collisions.
            if indexed_subject.endswith(norm):
                return True

    return False


def get_sent_timestamp(url: str, entry_title: str = "") -> Optional[int]:
    """
    Return the Unix timestamp when the entry was sent, or None if not found.
    Checks both URL index and title index (same precedence as has_been_sent_via_email).
    """
    indexes = fetch_sent_indexes()

    if url in indexes["url"]:
        return indexes["url"][url]

    # LEGACY FALLBACK — expires 2026-12-02. Remove this block after that date.
    if entry_title and time.time() < 1796169600:  # 2026-12-02 00:00:00 UTC
        norm = entry_title.lower().strip()
        for indexed_subject, ts in indexes["title"].items():
            if indexed_subject.endswith(norm):
                return ts

    return None


def get_all_sent_urls() -> dict:
    """Return the URL index {url: timestamp} directly."""
    return fetch_sent_indexes()["url"]


def invalidate_cache():
    """Force the next call to re-scan IMAP."""
    global _cache, _cache_loaded_at
    _cache = None
    _cache_loaded_at = 0
