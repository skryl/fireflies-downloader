# Fireflies Downloader

#!/usr/bin/env python3
"""
Download all Fireflies meeting videos to a local folder.

Auth: Authorization: Bearer <API_KEY>
GraphQL endpoint: https://api.fireflies.ai/graphql

Notes:
- video_url is a signed URL that expires ~24h; rerun script to regenerate URLs if needed.
- Some meetings won't have video_url (video capture disabled, platform limitations, etc).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

GQL_ENDPOINT = "https://api.fireflies.ai/graphql"


TRANSCRIPTS_QUERY = """
query Transcripts($limit: Int!, $skip: Int!, $mine: Boolean, $fromDate: DateTime, $toDate: DateTime, $channelId: String) {
  transcripts(limit: $limit, skip: $skip, mine: $mine, fromDate: $fromDate, toDate: $toDate, channel_id: $channelId) {
    id
    title
    dateString
    duration
    video_url
  }
}
"""


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_date_like(s: str) -> str:
    """
    Accepts:
      - YYYY-MM-DD
      - ISO8601 like 2025-12-01T10:30:00Z or with offset
    Returns ISO8601 string in UTC with Z suffix.
    """
    s = s.strip()
    if not s:
        raise ValueError("empty date")

    # Date only
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return _iso_utc(dt)

    # ISO datetime, maybe with Z
    s2 = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s2)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return _iso_utc(dt)


def sanitize_filename(name: str, max_len: int = 140) -> str:
    name = name.strip()
    name = re.sub(r"\s+", " ", name)
    # Replace illegal path chars on mac/windows/linux conservatively
    name = re.sub(r'[\/\\:\*\?"<>\|\x00-\x1F]', "_", name)
    name = name.strip(" ._")
    if not name:
        name = "untitled"
    if len(name) > max_len:
        name = name[:max_len].rstrip(" ._")
    return name


def gql_post(session: requests.Session, api_key: str, query: str, variables: Dict[str, Any], timeout_s: int = 60) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = session.post(
        GQL_ENDPOINT,
        headers=headers,
        json={"query": query, "variables": variables},
        timeout=timeout_s,
    )

    # Basic 429 handling
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After")
        wait_s = int(retry_after) if (retry_after and retry_after.isdigit()) else 30
        raise RuntimeError(f"Rate limited (HTTP 429). Retry after ~{wait_s}s.")

    resp.raise_for_status()
    payload = resp.json()

    if "errors" in payload and payload["errors"]:
        # Surface GraphQL errors clearly
        raise RuntimeError("GraphQL errors:\n" + json.dumps(payload["errors"], indent=2))

    data = payload.get("data")
    if data is None:
        raise RuntimeError(f"Unexpected response (no data): {payload}")
    return data


def iter_transcripts(
    session: requests.Session,
    api_key: str,
    limit: int,
    mine: bool,
    from_date: Optional[str],
    to_date: Optional[str],
    channel_id: Optional[str],
    throttle_s: float,
) -> Iterable[Dict[str, Any]]:
    skip = 0
    while True:
        variables = {
            "limit": limit,
            "skip": skip,
            "mine": mine,
            "fromDate": from_date,
            "toDate": to_date,
            "channelId": channel_id,
        }

        data = gql_post(session, api_key, TRANSCRIPTS_QUERY, variables)
        batch = data.get("transcripts") or []
        if not batch:
            return

        for t in batch:
            yield t

        # Pagination via skip/limit (max 50 per docs)
        got = len(batch)
        skip += got
        if got < limit:
            return

        if throttle_s > 0:
            time.sleep(throttle_s)


def download_stream(
    session: requests.Session,
    url: str,
    dest: Path,
    *,
    resume: bool = True,
    timeout_s: int = 120,
    chunk_bytes: int = 1024 * 1024,
) -> Tuple[bool, str]:
    """
    Returns (downloaded_now, message).
    downloaded_now=False can mean "already exists" or "skipped".
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    headers: Dict[str, str] = {}
    mode = "wb"
    existing = dest.exists()
    start_at = 0

    if existing and resume:
        start_at = dest.stat().st_size
        if start_at > 0:
            headers["Range"] = f"bytes={start_at}-"
            mode = "ab"

    # Probe with streaming GET
    with session.get(url, stream=True, headers=headers, timeout=timeout_s, allow_redirects=True) as r:
        # If server doesn't support Range, restart from scratch
        if r.status_code == 416:  # Range Not Satisfiable
            dest.unlink(missing_ok=True)
            return download_stream(session, url, dest, resume=False, timeout_s=timeout_s, chunk_bytes=chunk_bytes)

        if r.status_code == 200 and "Range" in headers:
            # Range ignored; restart
            dest.unlink(missing_ok=True)
            return download_stream(session, url, dest, resume=False, timeout_s=timeout_s, chunk_bytes=chunk_bytes)

        r.raise_for_status()

        total = None
        if "Content-Length" in r.headers:
            try:
                total = int(r.headers["Content-Length"])
            except ValueError:
                total = None

        # If file already exists and we didn't request range, just skip
        if existing and not resume:
            return (False, "exists")

        bytes_written = 0
        with open(dest, mode) as f:
            for chunk in r.iter_content(chunk_size=chunk_bytes):
                if not chunk:
                    continue
                f.write(chunk)
                bytes_written += len(chunk)

    if existing and bytes_written == 0:
        return (False, "exists")
    return (True, f"downloaded {bytes_written} bytes")


def main() -> int:
    p = argparse.ArgumentParser(description="Download all Fireflies meeting videos (via Fireflies GraphQL API).")
    p.add_argument("--api-key", default=os.environ.get("FIREFLIES_API_KEY"), help="Fireflies API key (or set FIREFLIES_API_KEY env var).")
    p.add_argument("--out", default="fireflies_videos", help="Output directory.")
    p.add_argument("--limit", type=int, default=50, help="Page size for transcripts query (max 50).")
    p.add_argument("--mine", action="store_true", default=True, help="Only fetch meetings where API key owner is organizer (default: true).")
    p.add_argument("--not-mine", dest="mine", action="store_false", help="Disable mine filter.")
    p.add_argument("--from", dest="from_date", default=None, help="Start date (YYYY-MM-DD or ISO8601).")
    p.add_argument("--to", dest="to_date", default=None, help="End date (YYYY-MM-DD or ISO8601).")
    p.add_argument("--channel-id", default=None, help="Filter to a Fireflies channel_id (optional).")
    p.add_argument("--throttle", type=float, default=0.25, help="Sleep seconds between GraphQL page fetches (default: 0.25).")
    p.add_argument("--resume", action="store_true", default=True, help="Resume partial downloads if possible (default: true).")
    p.add_argument("--no-resume", dest="resume", action="store_false", help="Disable resume.")
    p.add_argument("--overwrite", action="store_true", default=False, help="Overwrite existing files.")
    p.add_argument("--dry-run", action="store_true", default=False, help="List what would be downloaded, but do not download.")
    args = p.parse_args()

    api_key = (args.api_key or "").strip()
    if not api_key:
        print("ERROR: Missing API key. Pass --api-key or set FIREFLIES_API_KEY.", file=sys.stderr)
        return 2

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.jsonl"

    from_iso = parse_date_like(args.from_date) if args.from_date else None
    to_iso = parse_date_like(args.to_date) if args.to_date else None

    # Load prior manifest for idempotency
    completed_ids: set[str] = set()
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("status") == "downloaded" and rec.get("transcript_id"):
                        completed_ids.add(str(rec["transcript_id"]))
                except json.JSONDecodeError:
                    continue

    session = requests.Session()

    total_seen = 0
    total_with_video = 0
    total_downloaded = 0
    total_skipped = 0

    for t in iter_transcripts(
        session=session,
        api_key=api_key,
        limit=min(max(args.limit, 1), 50),
        mine=bool(args.mine),
        from_date=from_iso,
        to_date=to_iso,
        channel_id=args.channel_id,
        throttle_s=max(args.throttle, 0.0),
    ):
        total_seen += 1
        tid = str(t.get("id", "")).strip()
        title = str(t.get("title", "")).strip()
        date_str = str(t.get("dateString", "")).strip()
        video_url = t.get("video_url")

        if not tid:
            continue

        if tid in completed_ids and not args.overwrite:
            total_skipped += 1
            continue

        if not video_url:
            # No video available for this transcript
            rec = {
                "ts": _iso_utc(datetime.now(timezone.utc)),
                "transcript_id": tid,
                "title": title,
                "dateString": date_str,
                "status": "no_video_url",
            }
            with open(manifest_path, "a", encoding="utf-8") as mf:
                mf.write(json.dumps(rec) + "\n")
            total_skipped += 1
            continue

        total_with_video += 1

        safe_title = sanitize_filename(title or "meeting")
        safe_date = sanitize_filename(date_str.replace(":", "-").replace("Z", ""), max_len=40) if date_str else "unknown_date"
        filename = f"{safe_date}__{safe_title}__{tid}.mp4"
        dest = out_dir / filename

        if dest.exists() and not args.overwrite:
            total_skipped += 1
            rec = {
                "ts": _iso_utc(datetime.now(timezone.utc)),
                "transcript_id": tid,
                "title": title,
                "dateString": date_str,
                "file": str(dest),
                "status": "exists",
            }
            with open(manifest_path, "a", encoding="utf-8") as mf:
                mf.write(json.dumps(rec) + "\n")
            continue

        if args.dry_run:
            print(f"[DRY RUN] Would download: {dest.name}")
            total_skipped += 1
            continue

        try:
            if args.overwrite and dest.exists():
                dest.unlink(missing_ok=True)

            downloaded_now, msg = download_stream(session, str(video_url), dest, resume=args.resume)
            status = "downloaded" if downloaded_now else "skipped"
            if downloaded_now:
                total_downloaded += 1
            else:
                total_skipped += 1

            rec = {
                "ts": _iso_utc(datetime.now(timezone.utc)),
                "transcript_id": tid,
                "title": title,
                "dateString": date_str,
                "file": str(dest),
                "status": status,
                "message": msg,
            }
            with open(manifest_path, "a", encoding="utf-8") as mf:
                mf.write(json.dumps(rec) + "\n")

        except Exception as e:
            rec = {
                "ts": _iso_utc(datetime.now(timezone.utc)),
                "transcript_id": tid,
                "title": title,
                "dateString": date_str,
                "file": str(dest),
                "status": "error",
                "error": str(e),
            }
            with open(manifest_path, "a", encoding="utf-8") as mf:
                mf.write(json.dumps(rec) + "\n")
            print(f"ERROR downloading {tid}: {e}", file=sys.stderr)

    print("\nDone.")
    print(f"Transcripts seen:        {total_seen}")
    print(f"With video_url:          {total_with_video}")
    print(f"Downloaded now:          {total_downloaded}")
    print(f"Skipped/no-video/exists: {total_skipped}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())