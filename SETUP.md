# Quick Setup Guide

## Prerequisites

Before you begin, make sure you have:
- [ ] Docker and Docker Compose installed
- [ ] Gmail account with 2-Step Verification enabled
- [ ] Kindle email address from your Amazon account

## Step-by-Step Setup

### 1. Get Your Gmail App Password

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** if not already enabled
3. Go to **App passwords** (search for it on the page)
4. Select **Mail** and **Other (Custom name)**
5. Name it "Webtoepub" and click **Generate**
6. **Copy the 16-character password** (it will only be shown once)

### 2. Find Your Kindle Email

1. Go to [Amazon Content & Devices](https://www.amazon.com/mycd)
2. Click **Preferences** tab
3. Scroll to **Personal Document Settings**
4. Find your **Send-to-Kindle Email Address** (e.g., `username@kindle.com`)
5. Under **Approved Personal Document E-mail List**, click **Add a new approved e-mail address**
6. Add your Gmail address and click **Add Address**

### 3. Clone and Configure

```bash
# Clone the repository
git clone <repository-url>
cd webtoepub

# Create secrets directory
mkdir -p secrets

# Copy and edit environment variables
cp .env.example .env
nano .env  # or use your favorite editor
```

Edit `.env` with your actual values:
```bash
SENDER_EMAIL=youremail@gmail.com
APP_PASSWORD=your16charpassword
TO_EMAIL=yourkindle@kindle.com
```

### 4. Create Mail Configuration

Create `secrets/mailconfig.json`:
```json
{
  "sender_email": "youremail@gmail.com",
  "app_password": "your16charpassword",
  "to_email": "yourkindle@kindle.com"
}
```

### 5. Configure Your Feeds

Edit `feed.input.json` with your desired feeds:

```json
{
  "feeds": [
    {
      "name": "The Wandering Inn",
      "url": "https://wanderinginn.com/feed/",
      "ignore": false
    },
    {
      "name": "Your Favorite Royal Road Story",
      "url": "https://www.royalroad.com/fiction/syndication/12345",
      "ignore": false
    }
  ],
  "dry_run": false
}
```

**How to find Royal Road feed URLs:**
1. Go to your story on Royal Road
2. Look for the RSS icon or add `/syndication/STORYID` to the fiction URL
3. Example: `https://www.royalroad.com/fiction/syndication/36049`

### 6. Start the Application

```bash
# Start in background
docker-compose up -d

# View logs
docker-compose logs -f

# Check if it's running
docker-compose ps
```

### 7. Access the Web Interface

Open your browser and go to: http://localhost:9000

You should see a list of sent items (will be empty initially).

### 8. Test the Setup

#### Option A: Wait for Automatic Check
The application checks for new chapters every 15 minutes by default.

#### Option B: Manual Trigger
Use the API to manually trigger a check:
```bash
curl -X POST http://localhost:9000/execute
```

#### Option C: Run in Debug Mode
Test without sending emails:
```bash
# Stop the container
docker-compose down

# Edit docker-compose.yml and change DEBUG_MODE to true
# Then restart
docker-compose up -d
```

## Verification Checklist

- [ ] Container is running: `docker-compose ps`
- [ ] Web UI is accessible at http://localhost:9000
- [ ] Logs show no errors: `docker-compose logs`
- [ ] Test email was received in Kindle library (or check spam)

## Common Issues

### Container Keeps Restarting

Check logs for errors:
```bash
docker-compose logs webtoepub
```

Common causes:
- Invalid Gmail credentials
- Missing or incorrect configuration files
- Volume permission issues

### No Emails Received

1. Check your Gmail "Sent" folder
2. Check Kindle email spam folder
3. Verify Gmail address is in Amazon's approved senders list
4. Check logs for "Failed to send email" errors

### Permission Denied Errors

Fix volume permissions:
```bash
sudo chmod -R 755 feeds/
sudo chown -R $USER:$USER feeds/
```

## Next Steps

Once setup is complete:

1. **Add More Feeds**: Edit `feed.input.json` and restart the container
2. **Customize Cleaning**: Edit `keywords.txt` to improve Royal Road watermark removal
3. **Adjust Timing**: Change `UPDATE_FREQUENCY_SECONDS` in docker-compose.yml
4. **Monitor Usage**: Watch logs to see when new chapters are detected

## Updating the Application

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d
```

## Stopping the Application

```bash
# Stop and remove containers
docker-compose down

# Stop, remove containers, and delete volumes
docker-compose down -v
```

## Getting Help

- Check the main [README.md](README.md) for detailed documentation
- Review logs: `docker-compose logs -f webtoepub`
- Check environment variables: `docker-compose config`

## Security Notes

- Never commit `.env` or `secrets/mailconfig.json` to git
- Use Gmail App Passwords, not your regular password
- Keep your configuration files secure with appropriate permissions:
  ```bash
  chmod 600 .env secrets/mailconfig.json
  ```
