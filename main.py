import logging
from db import get_entries
from fastapi import FastAPI
from datetime import datetime
from utils import custom_logger
import uvicorn
from feeder import execute

app = FastAPI()

@app.get("/status")
async def get_status():
    """
    Returns the current timestamp.
    """
    now = datetime.utcnow()  # Get current time in UTC
    timestamp = now.isoformat() + "Z" # Format as ISO 8601 string with Z for UTC
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


# For running the app locally (for development)
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=True)

# https://browse.sirius.moonblade.work/api/public/dl/-ZyX3mJU
