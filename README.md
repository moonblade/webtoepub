# Web To EPUB

An automated web novel/series to EPUB converter and delivery system. This application monitors RSS feeds from web fiction sites, automatically converts new chapters to EPUB format, and delivers them directly to your Kindle email address.

## Overview

This project automates the workflow of reading web fiction on your e-reader:
1. **Monitor**: Continuously checks RSS feeds for new chapters from sites like Royal Road and The Wandering Inn
2. **Convert**: Downloads and converts web pages to clean EPUB files with custom CSS styling
3. **Clean**: Removes ads, watermarks, images, and other unwanted content
4. **Deliver**: Sends EPUB files directly to your Kindle email address via Gmail
5. **Track**: Maintains a database of processed chapters and provides a web UI to view history

### Key Features

- 📚 **RSS Feed Monitoring**: Automatically detects new chapters from multiple feeds
- 📖 **EPUB Conversion**: Converts HTML to well-formatted EPUB using Pandoc
- 🧹 **Content Cleaning**: Removes ads, watermarks, and unwanted elements (site-specific cleaning for Royal Road and Wandering Inn)
- 📧 **Email Delivery**: Sends EPUBs directly to Kindle via Gmail SMTP
- 🗄️ **Database Tracking**: TinyDB-based tracking to avoid duplicate processing
- 🌐 **Web UI**: FastAPI-based dashboard to view sent items and manage history
- ↩️ **Revert Feature**: Re-download and resend chapters via the web interface
- 📦 **Batch Processing**: Smart batching for new books (compiles multiple chapters into one EPUB)
- 🔄 **Periodic Updates**: Configurable automatic checking for new content
- 🐳 **Docker Support**: Easy deployment with Docker

### Supported Sites

- **Royal Road**: Full support including table of contents scraping for complete books
- **The Wandering Inn**: Custom cleaning for optimal reading experience
- **Any RSS Feed**: Generic RSS feed support with customizable cleaning

## Screenshots

**Kindle screen after receiving a chapter:**

<img width="593" alt="Kindle screenshot" src="https://user-images.githubusercontent.com/9362269/232269180-67b13efa-d80c-428d-93c4-6cba9575b0f4.png">

**Web UI showing sent items with revert functionality:**

(Your sent items are displayed with timestamps and a revert button to re-process any chapter)

## Architecture

- **FastAPI**: Web server and REST API
- **TinyDB**: Lightweight JSON-based database for tracking processed entries
- **Pypandoc**: HTML to EPUB conversion
- **BeautifulSoup**: HTML parsing and content cleaning
- **feedparser**: RSS feed parsing
- **Gmail SMTP**: Email delivery service

## Prerequisites

- Python 3.9+
- Docker & Docker Compose (for containerized deployment)
- Gmail account with App Password enabled
- Kindle email address (from Amazon account settings)

## Setup Instructions

### Option 1: Docker Compose (Recommended)

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd webtoepub
   ```

2. **Create configuration files:**

   Create `secrets/mailconfig.json`:
   ```json
   {
     "sender_email": "your-email@gmail.com",
     "app_password": "your-gmail-app-password",
     "to_email": "your-kindle-email@kindle.com"
   }
   ```

   Create `feed.input.json` with your feeds:
   ```json
   {
     "feeds": [
       {
         "name": "The Wandering Inn",
         "url": "https://wanderinginn.com/feed/",
         "ignore": false
       },
       {
         "name": "Your Royal Road Story",
         "url": "https://www.royalroad.com/fiction/syndication/12345",
         "ignore": false
       }
     ],
     "dry_run": false
   }
   ```

3. **Create docker-compose.yml:**
   ```yaml
   version: '3.8'

   services:
     webtoepub:
       build: .
       container_name: webtoepub
       ports:
         - "9000:9000"
       volumes:
         - ./feeds:/feeds
         - ./secrets/mailconfig.json:/app/secrets/mailconfig.json:ro
         - ./feed.input.json:/app/feed.input.json:ro
         - ./keywords.txt:/app/keywords.txt:ro
       environment:
         - SENDER_EMAIL=${SENDER_EMAIL}
         - APP_PASSWORD=${APP_PASSWORD}
         - TO_EMAIL=${TO_EMAIL}
         - DOWNLOAD_PATH=/feeds
         - UPDATE_FREQUENCY_SECONDS=900  # 15 minutes
         - DEBUG_MODE=false
         - MAX_BATCH_SIZE=20
         - ENTRY_THRESHOLD_FOR_NEW_BOOK=5
       restart: unless-stopped
   ```

4. **Create .env file (optional):**
   ```bash
   SENDER_EMAIL=your-email@gmail.com
   APP_PASSWORD=your-gmail-app-password
   TO_EMAIL=your-kindle-email@kindle.com
   ```

5. **Start the application:**
   ```bash
   docker-compose up -d
   ```

6. **Access the web UI:**
   Open http://localhost:9000 in your browser

### Option 2: Local Development Setup

1. **Clone and setup virtual environment:**
   ```bash
   git clone <repository-url>
   cd webtoepub
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create configuration files** (same as Docker setup above)

4. **Set environment variables:**
   ```bash
   export SENDER_EMAIL="your-email@gmail.com"
   export APP_PASSWORD="your-gmail-app-password"
   export TO_EMAIL="your-kindle-email@kindle.com"
   export DOWNLOAD_PATH="/tmp/feeds"
   export UPDATE_FREQUENCY_SECONDS=900
   ```

5. **Run the application:**
   ```bash
   # Using Make
   make run

   # Or directly
   python main.py
   ```

6. **Access the web UI:**
   Open http://localhost:9000 in your browser

### Getting Gmail App Password

1. Go to your Google Account settings: https://myaccount.google.com/
2. Security → 2-Step Verification (must be enabled)
3. Scroll down to "App passwords"
4. Select "Mail" and "Other (Custom name)"
5. Name it "Webtoepub" and generate
6. Copy the 16-character password (no spaces)

### Finding Your Kindle Email

1. Go to Amazon.com → Accounts & Lists → Content & Devices
2. Click "Preferences" tab
3. Scroll to "Personal Document Settings"
4. Find your "Send-to-Kindle Email Address" (e.g., `username@kindle.com`)
5. Add your Gmail address to "Approved Personal Document E-mail List"

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SENDER_EMAIL` | - | Gmail address to send from |
| `APP_PASSWORD` | - | Gmail app password |
| `TO_EMAIL` | - | Kindle email address |
| `DOWNLOAD_PATH` | `/feeds` | Directory to store downloads and database |
| `UPDATE_FREQUENCY_SECONDS` | `900` | How often to check for new chapters (seconds) |
| `DEBUG_MODE` | `false` | Enable debug mode (dry run, limited feeds) |
| `MAX_BATCH_SIZE` | `20` | Maximum emails to send in one batch |
| `ENTRY_THRESHOLD_FOR_NEW_BOOK` | `5` | Number of unprocessed entries to trigger compiled ebook creation |
| `FEEDURL` | - | URL to fetch remote feed list (optional) |
| `WANDERING_INN_URL_FRAGMENT` | `wanderinginn` | URL fragment to detect Wandering Inn entries |
| `TEST_FILE` | - | Path to test file for volume mount verification |

### Feed Configuration (feed.input.json)

```json
{
  "feeds": [
    {
      "name": "Story Name",
      "url": "https://example.com/feed/",
      "ignore": false,
      "dry_run": false
    }
  ],
  "dry_run": false
}
```

- `name`: Display name for the feed
- `url`: RSS feed URL
- `ignore`: Skip this feed if true
- `dry_run`: Test mode (don't send emails) if true

### Keywords Configuration (keywords.txt)

Add keywords (one per line) to identify and remove watermarks/ads from Royal Road chapters:
```
patreon
royal road
support
author
chapter
```

## API Endpoints

- `GET /` - Web UI showing sent items
- `GET /status` - Returns current timestamp
- `GET /sent_items` - JSON list of all processed entries
- `POST /execute` - Manually trigger feed processing
- `POST /revert/{link}` - Revert a processed entry (removes from DB and deletes files)

## Usage

### Web Interface

1. Navigate to http://localhost:9000
2. View all sent items with timestamps
3. Click "Revert" button to re-process any chapter
4. Confirmation dialog prevents accidental reverts

### Manual Execution

```bash
# Run once manually
make feeder

# Run with dry-run mode
DEBUG_MODE=true python feeder.py
```

### Building Docker Image

```bash
# Build image
make build

# Or manually
docker build -t webtoepub .
```

## File Structure

```
webtoepub/
├── db.py                 # Database operations (TinyDB)
├── models.py             # Pydantic models for data structures
├── feeder.py             # Feed processing and EPUB conversion logic
├── mail.py               # Gmail SMTP integration
├── main.py               # FastAPI web server and API endpoints
├── utils.py              # Utility functions (logging, file operations)
├── webtoepub.py          # Legacy conversion script
├── Dockerfile            # Docker container configuration
├── requirements.txt      # Python dependencies
├── Makefile              # Build and run commands
├── epub.css              # EPUB styling
├── keywords.txt          # Watermark detection keywords
├── feed.input.json       # Feed configuration
├── templates/
│   └── index.html        # Web UI template
└── secrets/
    └── mailconfig.json   # Email credentials (not in git)
```

## How It Works

### Processing Flow

1. **Feed Retrieval**: Fetches feed list from remote URL or local `feed.input.json`
2. **Entry Detection**: Parses RSS feeds and identifies new entries
3. **Download**: Retrieves HTML content from chapter URLs
4. **Cleaning**: Site-specific cleaning removes unwanted elements
5. **Conversion**: Pypandoc converts cleaned HTML to EPUB with custom CSS
6. **Batching**: Groups emails and checks batch size limits
7. **Delivery**: Sends EPUB files via Gmail SMTP
8. **Database Update**: Records processed entries in TinyDB

### Smart Book Compilation

When more than 5 unprocessed entries are detected for a feed:
- For Royal Road: Scrapes table of contents for all chapters
- Downloads and converts all chapters
- Compiles them into a single EPUB with table of contents
- Sends one compiled book instead of individual chapters

### Content Cleaning

**Royal Road:**
- Extracts chapter content from `div.chapter-inner.chapter-content`
- Removes watermark paragraphs using keyword matching
- Filters elements with specific sentence and word count patterns

**The Wandering Inn:**
- Extracts content from `div.elementor-widget-theme-post-content`
- Removes video players, YouTube embeds, images, and galleries
- Preserves chapter structure and formatting

## Troubleshooting

### Common Issues

**"Failed to send email" errors:**
- Verify Gmail App Password is correct (not your regular password)
- Check that 2-Step Verification is enabled on your Google account
- Ensure your Gmail address is in Kindle's approved sender list

**"EPUB file not found" errors:**
- Check DOWNLOAD_PATH exists and is writable
- Verify Pandoc is installed (included in pypandoc_binary)
- Check logs for download or conversion errors

**No new chapters detected:**
- Verify RSS feed URL is correct and accessible
- Check if entries are already in database (`/feeds/db.json`)
- Use revert feature to re-process specific chapters

**Docker container exits:**
- Check environment variables are set correctly
- Verify volume mounts exist and have proper permissions
- Review logs: `docker logs webtoepub`

### Debug Mode

Enable debug mode to test without sending emails:
```bash
DEBUG_MODE=true python main.py
```

This will:
- Only process first 2 feeds
- Set dry_run mode (no emails sent)
- Still add entries to database

## Contributing

Contributions are welcome! Areas for improvement:
- Additional site-specific cleaners
- Enhanced EPUB formatting and styling
- Web UI improvements (search, filters, bulk operations)
- Alternative email providers (SendGrid, AWS SES)
- Better error handling and retry logic

## License

[Your License Here]

## Acknowledgments

- Built for automating the delivery of web fiction to e-readers
- Originally designed for personal use with The Wandering Inn and Royal Road stories
- Now evolved into a full-featured feed-to-ebook automation system
