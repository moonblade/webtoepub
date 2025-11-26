import logging
import os
from db import get_entries
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from datetime import datetime
from utils import custom_logger
import uvicorn
from feeder import execute
import asyncio
from fastapi.templating import Jinja2Templates

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

# @app.on_event("startup")
# async def startup_event():
#     if not DEBUG_MODE:
#         asyncio.create_task(run_periodic_updates())

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=True)
