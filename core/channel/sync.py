from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

from core.channel.models import ChannelProfile, ChannelVideo, SyncResult
from core.db.memory import MemoryDB

logger = logging.getLogger(__name__)


def parse_iso8601_duration(duration_str: str) -> int:
    """Parse ISO 8601 duration (e.g. PT1M15S, PT45S) into seconds."""
    if not duration_str or not duration_str.startswith("PT"):
        return 0
    pattern = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
    match = pattern.match(duration_str)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def is_short_video(title: str, description: str, duration_seconds: int, video_url: str = "") -> bool:
    """Determine if a video is a YouTube Short."""
    if "/shorts/" in video_url:
        return True
    text = f"{title} {description}".lower()
    if "#shorts" in text or "#short" in text:
        return True
    if 0 < duration_seconds <= 180:
        return True
    return False


class ChannelSyncEngine:
    """Synchronizes videos from channel uploads playlist incrementally."""

    def __init__(self, db: MemoryDB, api_key: str | None = None):
        self.db = db
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")

    def sync_channel(self, profile_data: dict[str, Any] | ChannelProfile, max_videos: int = 100) -> SyncResult:
        if isinstance(profile_data, ChannelProfile):
            profile = profile_data
        else:
            profile = ChannelProfile.from_dict(profile_data)

        if not profile.id:
            db_prof = self.db.get_channel_profile(handle=profile.handle, channel_id=profile.channel_id)
            if db_prof:
                profile.id = db_prof["id"]
            else:
                saved = self.db.save_channel_profile(profile.to_dict())
                profile.id = saved.get("id")

        if not profile.id:
            return SyncResult(status="failed", errors=["Channel profile could not be identified or saved."])

        uploads_id = profile.uploads_playlist_id
        if not uploads_id and profile.channel_id:
            uploads_id = "UU" + profile.channel_id.lstrip("UC")
            profile.uploads_playlist_id = uploads_id

        run_id = self.db.record_sync_run(channel_profile_id=profile.id, status="running")

        try:
            videos: list[dict[str, Any]] = []

            # 1. Fetch via API if key available
            if self.api_key and uploads_id:
                videos = self._fetch_via_api(uploads_id, max_videos)

            # 2. Fetch via yt-dlp if API failed or no key
            if not videos and uploads_id:
                videos = self._fetch_via_ytdlp(uploads_id, max_videos)

            # 3. Fallback: if offline / test mock and no videos
            if not videos and not os.getenv("CI"):
                logger.info("No remote videos retrieved for %s; sync completed with 0 new videos", profile.handle)

            discovered_count = len(videos)
            added_count = 0
            shorts_count = 0

            if videos:
                for v in videos:
                    v["channel_profile_id"] = profile.id
                    if v.get("is_short"):
                        shorts_count += 1
                added_count = self.db.save_channel_videos(profile.id, videos)

            self.db.record_sync_run(
                channel_profile_id=profile.id,
                status="success",
                videos_discovered=discovered_count,
                videos_added=added_count,
                run_id=run_id,
            )

            # If auto-analyze is enabled, trigger recipe extraction
            if profile.auto_analyze_enabled and added_count > 0:
                self._auto_extract_recipes(profile.id)

            return SyncResult(
                status="success",
                videos_discovered=discovered_count,
                videos_added=added_count,
                shorts_added=shorts_count,
            )
        except Exception as e:
            logger.exception("Channel sync failed for profile %s: %s", profile.handle, e)
            self.db.record_sync_run(
                channel_profile_id=profile.id,
                status="failed",
                error_message=str(e),
                run_id=run_id,
            )
            return SyncResult(status="failed", errors=[str(e)])

    def _fetch_via_api(self, uploads_playlist_id: str, max_results: int) -> list[dict[str, Any]]:
        videos = []
        page_token = None
        base_url = "https://www.googleapis.com/youtube/v3/playlistItems"

        while len(videos) < max_results:
            params = {
                "key": self.api_key,
                "part": "snippet,contentDetails",
                "playlistId": uploads_playlist_id,
                "maxResults": min(50, max_results - len(videos)),
            }
            if page_token:
                params["pageToken"] = page_token

            resp = requests.get(base_url, params=params, timeout=10)
            if resp.status_code != 200:
                break
            data = resp.json()
            items = data.get("items", [])
            if not items:
                break

            video_ids = [it["contentDetails"]["videoId"] for it in items if "contentDetails" in it and "videoId" in it["contentDetails"]]
            details_map = self._fetch_video_details(video_ids)

            for item in items:
                snippet = item.get("snippet", {})
                vid = item.get("contentDetails", {}).get("videoId")
                if not vid:
                    continue

                title = snippet.get("title", "")
                desc = snippet.get("description", "")
                pub = snippet.get("publishedAt")
                thumb = snippet.get("thumbnails", {}).get("high", {}).get("url", "")
                v_detail = details_map.get(vid, {})
                duration = v_detail.get("duration_seconds", 0)

                short_flag = is_short_video(title, desc, duration, f"https://www.youtube.com/watch?v={vid}")

                videos.append({
                    "youtube_video_id": vid,
                    "title": title,
                    "description": desc,
                    "published_at": pub,
                    "duration_seconds": duration,
                    "is_short": short_flag,
                    "video_url": f"https://www.youtube.com/watch?v={vid}",
                    "thumbnail_url": thumb,
                    "etag": item.get("etag", ""),
                    "raw_metadata": snippet,
                })

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return videos

    def _fetch_video_details(self, video_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not video_ids:
            return {}
        result = {}
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "key": self.api_key,
            "part": "contentDetails,statistics",
            "id": ",".join(video_ids),
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    vid = item["id"]
                    cd = item.get("contentDetails", {})
                    dur_str = cd.get("duration", "")
                    dur_sec = parse_iso8601_duration(dur_str)
                    result[vid] = {
                        "duration_seconds": dur_sec,
                        "statistics": item.get("statistics", {}),
                    }
        except Exception:
            pass
        return result

    def _fetch_via_ytdlp(self, uploads_playlist_id: str, max_results: int) -> list[dict[str, Any]]:
        videos = []
        try:
            import yt_dlp
            url = f"https://www.youtube.com/playlist?list={uploads_playlist_id}"
            ydl_opts = {
                "extract_flat": True,
                "playlistend": max_results,
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                entries = info.get("entries") or []
                for entry in entries:
                    if not entry:
                        continue
                    vid = entry.get("id")
                    if not vid:
                        continue
                    title = entry.get("title") or ""
                    desc = entry.get("description") or ""
                    dur = int(entry.get("duration") or 0)
                    v_url = entry.get("url") or f"https://www.youtube.com/watch?v={vid}"
                    short_flag = is_short_video(title, desc, dur, v_url)

                    videos.append({
                        "youtube_video_id": vid,
                        "title": title,
                        "description": desc,
                        "published_at": None,
                        "duration_seconds": dur,
                        "is_short": short_flag,
                        "video_url": v_url,
                        "thumbnail_url": entry.get("thumbnail") or "",
                        "etag": "",
                        "raw_metadata": entry,
                    })
        except Exception:
            pass
        return videos

    def _auto_extract_recipes(self, channel_profile_id: int) -> None:
        try:
            from core.channel.recipe_extractor import RecipeExtractor
            extractor = RecipeExtractor(self.db)
            # Incremental sync: only extract for videos that have not yet been analyzed
            videos = self.db.get_unextracted_channel_videos(channel_profile_id)
            for v in videos:
                extractor.extract_and_save(channel_profile_id, v)
        except Exception as e:
            logger.warning("Auto recipe extraction encountered an error: %s", e)
