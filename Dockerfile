# Use Python 3.9 slim image as base
FROM python:3.9-slim

# Set working directory in container
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

RUN mkdir -p /feeds && chmod 744 /feeds

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY db.py .
COPY epub.css .
COPY feeder.py .
COPY feed.input.json .
COPY keywords.txt .
COPY mail.py .
COPY main.py .
COPY models.py .
COPY utils.py .
COPY templates/ templates/

# Expose the port the app runs on
EXPOSE 9000

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
