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


⸻

Authentication

You need a Fireflies API key.

Option A: Environment variable (recommended)

export FIREFLIES_API_KEY="YOUR_API_KEY"

Option B: CLI flag

python download_fireflies_videos.py --api-key "YOUR_API_KEY"


⸻

Usage

Download everything (default output folder)

python download_fireflies_videos.py

Choose an output folder

python download_fireflies_videos.py --out ./fireflies_videos

Dry run (list what would be downloaded)

python download_fireflies_videos.py --dry-run


⸻

Filtering

Date filtering

You can filter transcripts by date using --from and --to.

From a date onward:

python download_fireflies_videos.py --from 2025-01-01

Bounded range:

python download_fireflies_videos.py --from 2025-01-01 --to 2025-12-01

Accepted formats:
	•	YYYY-MM-DD
	•	ISO 8601 (e.g. 2025-12-01T10:30:00Z)

Channel filtering (optional)

python download_fireflies_videos.py --channel-id YOUR_CHANNEL_ID

Mine vs not mine

By default the script fetches meetings where the API key owner is the organizer (--mine).

To disable that filter:

python download_fireflies_videos.py --not-mine


⸻

Resume / Overwrite Behavior

By default, the script:
	•	Skips files that already exist
	•	Resumes partial downloads when possible
	•	Skips transcripts already marked as downloaded in manifest.jsonl

Disable resume

python download_fireflies_videos.py --no-resume

Overwrite existing files

python download_fireflies_videos.py --overwrite


⸻

Rate Limiting / Throttling

If you hit 429 responses or want to be gentle with the API, increase the throttle between transcript page requests:

python download_fireflies_videos.py --throttle 1.0


⸻

Output

Videos are saved into the output directory, e.g.:

fireflies_videos/
  2025-12-01T10-30-00__My Meeting Title__<transcript_id>.mp4
  manifest.jsonl

manifest.jsonl

Append-only log of every processed transcript. Each line is a JSON object with fields such as:
	•	transcript_id
	•	status (downloaded, exists, no_video_url, error)
	•	file (when applicable)
	•	error (when applicable)

This is what makes re-runs safe and helps you audit what happened.

⸻

Common Gotchas
	•	No video_url
Video may not have been recorded, video recording may be disabled in Fireflies settings, or your plan may not include video exports.
	•	Signed URL expired
The video_url is a signed link and can expire. Re-run the script to fetch fresh URLs.
	•	Rate limited (HTTP 429)
Increase --throttle and rerun.

⸻

Security
	•	Do not commit API keys into the repo.
	•	Prefer environment variables (FIREFLIES_API_KEY) or a secret manager.

⸻

Roadmap / Ideas

PRs welcome. Common enhancements:
	•	Parallel downloads with configurable worker count
	•	Optional upload to S3/GCS after download
	•	Content-Length / checksum verification
	•	Custom filename templates / collision handling

⸻

License

Add your preferred license (MIT / Apache-2.0 / etc.). This repo currently ships without a license by default.


