# Fireflies Video Downloader

Download all available meeting video recordings from the Fireflies.ai API to your local machine.

This script:
- Pages through transcripts via the Fireflies GraphQL API
- Pulls each transcript’s `video_url` (a signed URL, when available)
- Downloads the video file to disk
- Writes a `manifest.jsonl` log so re-runs are safe/idempotent

> **Note:** Not every transcript will have a `video_url` (depends on your Fireflies settings/plan and whether video was recorded).

---

## Repository Contents

- `download_fireflies_videos.py` — Main script
- `README.md` — This file

---

## Requirements

- Python 3.9+
- `requests`

Install dependencies:

```bash
pip install requests
```

---

## Authentication

You need a Fireflies API key.

### Option A: Environment variable (recommended)

```bash
export FIREFLIES_API_KEY="YOUR_API_KEY"
```

### Option B: CLI flag

```bash
python download_fireflies_videos.py --api-key "YOUR_API_KEY"
```

---

## Usage

### Download everything (default output folder)

```bash
python download_fireflies_videos.py
```

### Choose an output folder

```bash
python download_fireflies_videos.py --out ./fireflies_videos
```

### Dry run (list what would be downloaded)

```bash
python download_fireflies_videos.py --dry-run
```

---

## Filtering

### Date filtering

You can filter transcripts by date using `--from` and `--to`.

From a date onward:

```bash
python download_fireflies_videos.py --from 2025-01-01
```

Bounded range:

```bash
python download_fireflies_videos.py --from 2025-01-01 --to 2025-12-01
```

Accepted formats:
- `YYYY-MM-DD`
- ISO 8601 (e.g. `2025-12-01T10:30:00Z`)

### Channel filtering (optional)

```bash
python download_fireflies_videos.py --channel-id YOUR_CHANNEL_ID
```

### Mine vs not mine

By default the script fetches meetings where the API key owner is the organizer (`--mine`).

To disable that filter:

```bash
python download_fireflies_videos.py --not-mine
```
