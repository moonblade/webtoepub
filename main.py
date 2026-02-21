import logging
import os
import re
from db import get_entries, get_all_feeds, add_feed, update_feed, delete_feed, migrate_feeds_from_json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from datetime import datetime
from utils import custom_logger
import uvicorn
from feeder import execute
import asyncio
from fastapi.templating import Jinja2Templates
from models import FeedItem
import feedparser

app = FastAPI()
logger = custom_logger(__name__)

templates = Jinja2Templates(directory="templates")
UPDATE_FREQUENCY_SECONDS = int(os.getenv("UPDATE_FREQUENCY_SECONDS", 60 * 15))
DEBUG_MODE = os.getenv("DEBUG_MODE", "false") == "true"

async def run_periodic_updates():
    while True:
        try:
            logger.info("Starting periodic update...")
            await _execute_task()
            logger.info("Periodic update complete.")
            await asyncio.sleep(UPDATE_FREQUENCY_SECONDS)
        except Exception as e:
            logger.exception(f"Error during periodic update: {e}")
            await asyncio.sleep(UPDATE_FREQUENCY_SECONDS)


async def _execute_task():
    await asyncio.to_thread(execute)

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """
    Returns a webpage with a list of sent items.
    """
    sent_items = get_entries()
    return templates.TemplateResponse("index.html", {"request": request, "sent_items": sent_items})

@app.get("/status")
async def get_status():
    """
    Returns the current timestamp.
    """
    now = datetime.utcnow()
    timestamp = now.isoformat() + "Z"
    return timestamp

@app.post("/execute")
async def _execute():
    execute()
    return "ok"

@app.get("/sent_items")
async def get_sent_items():
    """
    Returns a list of items that have been sent.
    """
    return get_entries()

@app.post("/revert/{link:path}")
async def revert_entry(link: str):
    """
    Reverts an entry by removing it from the database and deleting associated files.
    """
    from db import delete_entry
    from utils import delete_entry_files
    
    # Get the entry before deleting to access its metadata
    entries = get_entries()
    entry_to_delete = None
    for entry in entries:
        if entry.link == link:
            entry_to_delete = entry
            break
    
    if not entry_to_delete:
        logger.error(f"Entry not found with link: {link}")
        return {"success": False, "message": "Entry not found"}
    
    # Delete from database
    deleted = delete_entry(link)
    
    if deleted:
        # Delete associated files
        download_path = os.getenv("DOWNLOAD_PATH", "/feeds")
        feed_title = entry_to_delete.dict().get("feed", {}).get("title", "")
        
        deleted_files = delete_entry_files(
            entry_to_delete.title,
            feed_title,
            download_path
        )
        
        logger.info(f"Reverted entry: {entry_to_delete.title} (deleted {deleted_files} files)")
        return {
            "success": True,
            "message": f"Entry reverted successfully. Deleted {deleted_files} files.",
            "title": entry_to_delete.title
        }
    else:
        logger.error(f"Failed to delete entry from database: {link}")
        return {"success": False, "message": "Failed to delete entry from database"}


# ============== Feed Configuration Endpoints ==============

@app.get("/configure", response_class=HTMLResponse)
async def configure_page(request: Request):
    migrate_feeds_from_json()
    feeds = get_all_feeds()
    return templates.TemplateResponse("configure.html", {"request": request, "feeds": feeds})


@app.get("/api/feeds")
async def api_get_feeds():
    migrate_feeds_from_json()
    feeds = get_all_feeds()
    return {"success": True, "feeds": [f.dict() for f in feeds]}


@app.post("/api/feeds")
async def api_add_feed(request: Request):
    data = await request.json()
    url = data.get("url", "").strip()
    name = data.get("name", "").strip()
    ignore = data.get("ignore", False)
    dry_run = data.get("dry_run", False)
    
    if not url:
        return {"success": False, "message": "URL is required"}
    if not name:
        return {"success": False, "message": "Name is required"}
    
    feed = FeedItem(name=name, url=url, ignore=ignore, dry_run=dry_run)
    success = add_feed(feed)
    
    if success:
        return {"success": True, "message": "Feed added successfully"}
    return {"success": False, "message": "Feed with this URL already exists"}


@app.put("/api/feeds")
async def api_update_feed(request: Request):
    data = await request.json()
    url = data.get("url", "").strip()
    
    if not url:
        return {"success": False, "message": "URL is required"}
    
    updates = {}
    if "name" in data:
        updates["name"] = data["name"].strip()
    if "ignore" in data:
        updates["ignore"] = data["ignore"]
    if "dry_run" in data:
        updates["dry_run"] = data["dry_run"]
    
    if not updates:
        return {"success": False, "message": "No updates provided"}
    
    success = update_feed(url, updates)
    if success:
        return {"success": True, "message": "Feed updated successfully"}
    return {"success": False, "message": "Feed not found"}


@app.delete("/api/feeds")
async def api_delete_feed(request: Request):
    data = await request.json()
    url = data.get("url", "").strip()
    
    if not url:
        return {"success": False, "message": "URL is required"}
    
    success = delete_feed(url)
    if success:
        return {"success": True, "message": "Feed deleted successfully"}
    return {"success": False, "message": "Feed not found"}


def strip_brackets_from_title(title: str) -> str:
    """Remove content within [] and () from title."""
    title = re.sub(r'\[.*?\]', '', title)
    title = re.sub(r'\(.*?\)', '', title)
    return title.strip()


@app.post("/api/feeds/fetch-title")
async def api_fetch_feed_title(request: Request):
    data = await request.json()
    url = data.get("url", "").strip()
    
    if not url:
        return {"success": False, "message": "URL is required"}
    
    try:
        parsed = feedparser.parse(url)
        if parsed.bozo and not parsed.entries:
            return {"success": False, "message": "Could not parse feed URL"}
        
        title = getattr(parsed.feed, 'title', '') or ''
        if not title:
            return {"success": False, "message": "Feed has no title"}
        
        clean_title = strip_brackets_from_title(title)
        return {"success": True, "title": clean_title, "original_title": title}
    except Exception as e:
        logger.error(f"Error fetching feed title: {e}")
        return {"success": False, "message": "Failed to fetch feed"}

# @app.on_event("startup")
# async def startup_event():
#     if not DEBUG_MODE:
#         asyncio.create_task(run_periodic_updates())

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=True)
