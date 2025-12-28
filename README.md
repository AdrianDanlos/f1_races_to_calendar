# F1 Calendar Sync

Automatically syncs Formula 1 races, qualifying, and sprint sessions to your Google Calendar. Runs on GitHub Actions or locally.

## Features

- ✅ Fetches F1 schedule from [f1api.dev](https://f1api.dev/api/current)
- ✅ Adds races, qualifying, and sprint sessions to Google Calendar automatically
- ✅ Updates existing events when schedules change
- ✅ Runs monthly to catch schedule updates
- ✅ Works on GitHub Actions (no local setup needed)

## Quick Setup (GitHub Actions)

### 1. Set Up Google Cloud

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable **Google Calendar API**: APIs & Services > Library > Search "Google Calendar API" > Enable
4. Create a Service Account:
   - APIs & Services > Credentials > Create Credentials > Service Account
   - Name it (e.g., "f1-calendar-sync")
   - Skip role assignment > Done
5. Create a Key:
   - Click the service account > Keys tab > Add Key > Create new key > JSON
   - Download the JSON file
   - Copy the service account email (looks like `xxx@xxx.iam.gserviceaccount.com`)

**Note**: You can reuse the same service account from your Barcelona calendar project!

### 2. Add GitHub Secrets

Go to your repo: Settings > Secrets and variables > Actions > New repository secret

- **`GOOGLE_SERVICE_ACCOUNT_JSON`** (Required): Paste entire contents of the JSON file
- **`USER_EMAIL`** (Required): Your Google Calendar email (e.g., `your-email@gmail.com`)
- **`CALENDAR_NAME`** (Required): Calendar name for F1 sessions (e.g., "F1 Calendar")

### 3. Run It

The workflow runs automatically on the 1st of each month, or trigger manually:
- Go to Actions tab > "Sync F1 Calendar" > Run workflow

**Note**: The calendar is created automatically and shared with your email. No manual calendar creation needed!

## What Gets Synced

- ✅ **Races** - All Formula 1 Grand Prix races
- ✅ **Qualifying** - Qualifying sessions for each race
- ✅ **Sprint Races** - Sprint race sessions (when available)
- ✅ **Sprint Qualifying** - Sprint qualifying sessions (when available)

Practice sessions (FP1, FP2, FP3) are not included, but can be added if needed.