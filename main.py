import logging
import os
from db import get_entries
from fastapi import FastAPI
from datetime import datetime
from utils import custom_logger
import uvicorn
from feeder import execute
import asyncio

app = FastAPI()
logger = custom_logger(__name__)


UPDATE_FREQUENCY_SECONDS = int(os.getenv("UPDATE_FREQUENCY_SECONDS", 60 * 15))

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

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(run_periodic_updates())

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=True)
