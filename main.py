from fastapi import FastAPI
from datetime import datetime

app = FastAPI()

@app.get("/status")
async def get_status():
    """
    Returns the current timestamp.
    """
    now = datetime.utcnow()  # Get current time in UTC
    timestamp = now.isoformat() + "Z" # Format as ISO 8601 string with Z for UTC

    return {"timestamp": timestamp}


# For running the app locally (for development)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) # host 0.0.0.0 makes the app accessible from outside the container if dockerized. If you are running locally only, you can use 127.0.0.1
