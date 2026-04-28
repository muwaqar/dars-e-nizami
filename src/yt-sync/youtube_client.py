"""
youtube_client.py - YouTube API interactions.
"""

import google_auth_oauthlib.flow
import google.auth
import googleapiclient.discovery
import googleapiclient.errors
import json
import time
import os
from pathlib import Path
from typing import Optional

from config import (
    SCOPES,
    API_SERVICE_NAME,
    API_VERSION,
    get_playlists,
    get_default_privacy,
    generate_title,
    get_prefix_from_title,
    get_part_from_title,
    get_date_from_title,
    video_sort_key,
    prefix_matches,
    get_client_secrets_file,
)


class YouTubeClient:
    def __init__(
        self,
        credentials_file: str = None,
        re_authenticate: bool = False,
    ):
        if credentials_file is None:
            credentials_file = get_client_secrets_file()
        self._credentials_path = Path("token.json")
        self._re_authenticate = re_authenticate
        self.youtube = self._authenticate(credentials_file)
        self._playlist_cache = {}
        self._uploads_cache = {}
        self._uploads_playlist_id = None

    def _authenticate(self, credentials_file: str):
        """Authenticate with YouTube API, caching tokens for reuse."""
        if self._re_authenticate and self._credentials_path.exists():
            print("Forcing re-authentication...")
            self._credentials_path.unlink()

        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
            credentials_file, SCOPES
        )

        if self._credentials_path.exists():
            try:
                with open(self._credentials_path, "r") as f:
                    token_data = json.load(f)
                token_data["type"] = "authorized_user"
                credentials, _ = google.auth.load_credentials_from_dict(
                    token_data, scopes=SCOPES
                )
                print("Loaded cached credentials.")
            except Exception:
                print("Cached credentials invalid, re-authenticating...")
                credentials = flow.run_local_server(port=0)
        else:
            credentials = flow.run_local_server(port=0)

        token_data = json.loads(credentials.to_json())
        token_data["type"] = "authorized_user"
        with open(self._credentials_path, "w") as f:
            json.dump(token_data, f, indent=2)

        return googleapiclient.discovery.build(
            API_SERVICE_NAME, API_VERSION, credentials=credentials
        )

    def get_playlist_videos(self, playlist_id: str) -> list[dict]:
        """Fetch all videos from a playlist, sorted by position."""
        if playlist_id in self._playlist_cache:
            return self._playlist_cache[playlist_id]

        videos = []
        next_page_token = None

        while True:
            response = (
                self.youtube.playlistItems()
                .list(
                    part="snippet",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token,
                )
                .execute()
            )

            for item in response.get("items", []):
                snippet = item["snippet"]
                videos.append(
                    {
                        "title": snippet["title"],
                        "video_id": snippet["resourceId"]["videoId"],
                        "position": snippet["position"],
                        "playlist_item_id": item["id"],
                    }
                )

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        videos.sort(key=lambda x: x["position"])
        self._playlist_cache[playlist_id] = videos
        return videos

    def find_video_by_title(self, playlist_id: str, title: str) -> Optional[dict]:
        """Find a video in playlist by title."""
        videos = self.get_playlist_videos(playlist_id)
        for video in videos:
            if video["title"] == title:
                return video
        return None

    def video_exists_in_playlist(self, playlist_id: str, title: str) -> bool:
        """Check if a video with given title exists in playlist."""
        return self.find_video_by_title(playlist_id, title) is not None

    def _title_matches(self, search_title: str, target_title: str) -> bool:
        """Check if titles match (case-insensitive, handles encoding differences)."""
        return search_title.strip().lower() == target_title.strip().lower()

    def _get_uploads_playlist_id(self) -> str:
        """Get the uploads playlist ID for the authenticated user's channel."""
        if self._uploads_playlist_id is not None:
            return self._uploads_playlist_id

        response = (
            self.youtube.channels()
            .list(
                mine=True,
                part="contentDetails",
            )
            .execute()
        )
        self._uploads_playlist_id = response["items"][0]["contentDetails"][
            "relatedPlaylists"
        ]["uploads"]
        return self._uploads_playlist_id

    def _get_uploads_videos(self) -> list[dict]:
        """Get all videos from uploads playlist (cached)."""
        uploads_playlist = self._get_uploads_playlist_id()
        if uploads_playlist not in self._uploads_cache:
            self._uploads_cache[uploads_playlist] = self.get_playlist_videos(
                uploads_playlist
            )
        return self._uploads_cache[uploads_playlist]

    def find_video_on_youtube(self, title: str) -> Optional[dict]:
        """
        Search for a video on YouTube by title.
        Returns video dict with id if found, None otherwise.
        Searches through the user's uploads playlist directly.
        """
        try:
            videos = self._get_uploads_videos()

            for video in videos:
                if self._title_matches(video["title"], title):
                    return {
                        "video_id": video["video_id"],
                        "title": video["title"],
                    }

        except Exception as e:
            print(f"      Search failed: {e}")

        return None

    def find_video_on_youtube_by_id(self, video_id: str) -> Optional[dict]:
        """
        Get video details by ID.
        Returns video dict if found, None otherwise.
        """
        try:
            response = self.youtube.videos().list(part="snippet", id=video_id).execute()
            items = response.get("items", [])
            if items:
                return {
                    "video_id": items[0]["id"],
                    "title": items[0]["snippet"]["title"],
                }
        except googleapiclient.errors.HttpError as e:
            print(f"      Video lookup failed: {e}")
        return None

    def upload_video(
        self, file_path: str, title: str, max_retries: int = 3
    ) -> Optional[str]:
        """
        Upload a video to YouTube.
        Returns video_id on success, None on failure.
        Uses exponential backoff for retries.
        """
        body = {
            "snippet": {
                "title": title,
                "description": f"Uploaded via Dars-e-Nizami Syncer",
                "tags": [],
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": get_default_privacy(),
                "selfDeclaredMadeForKids": False,
            },
        }

        insert_request = self.youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=googleapiclient.http.MediaFileUpload(
                file_path, chunksize=-1, resumable=True
            ),
        )

        for attempt in range(max_retries):
            try:
                response = self._upload_with_progress(insert_request)
                if response:
                    return response["id"]
            except googleapiclient.errors.HttpError as e:
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    print(
                        f"      Retry {attempt + 1}/{max_retries} after {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    print(f"      Upload failed: {e}")
                    return None

        return None

    def _upload_with_progress(self, request):
        """Execute upload with simple progress indication."""
        print("      Uploading... ", end="", flush=True)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(
                    f"\r      Uploading... {int(status.progress() * 100)}% ",
                    end="",
                    flush=True,
                )
        print("Done!")
        return response

    def add_to_playlist(self, playlist_id: str, video_id: str, position: int) -> bool:
        """
        Add a video to playlist at specific position.
        Position is 0-indexed.
        """
        body = {
            "snippet": {
                "playlistId": playlist_id,
                "position": position,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        }

        try:
            self.youtube.playlistItems().insert(part="snippet", body=body).execute()
            return True
        except googleapiclient.errors.HttpError as e:
            print(f"      Failed to add to playlist: {e}")
            return False

    def calculate_position(
        self,
        playlist_id: str,
        yt_prefix: str,
        part: str | None,
        date: str,
        sort_order: str = "asc",
    ) -> int:
        """
        Calculate the correct position for a new video in playlist.
        Sorts by part number (asc), then date (asc) for 'asc' mode.
        Sorts by date only (desc) for 'desc' mode.
        """
        videos = self.get_playlist_videos(playlist_id)

        if sort_order == "desc":
            new_video_sort_key = (date,)
        else:
            new_video_sort_key = (int(part) if part else float("inf"), date)

        position = 0
        for video in videos:
            video_prefix = get_prefix_from_title(video["title"])
            if not prefix_matches(video_prefix, yt_prefix):
                continue

            video_sort = video_sort_key(video["title"], sort_order)
            if video_sort < new_video_sort_key:
                position += 1

        return position

    def update_playlist_item_position(
        self, playlist_item_id: str, playlist_id: str, new_position: int
    ) -> bool:
        """
        Update a video's position in playlist.
        """
        try:
            response = (
                self.youtube.playlistItems()
                .list(part="snippet", id=playlist_item_id)
                .execute()
            )
            items = response.get("items", [])
            if not items:
                return False

            resource_id = items[0]["snippet"]["resourceId"]

            self.youtube.playlistItems().update(
                part="snippet",
                body={
                    "id": playlist_item_id,
                    "snippet": {
                        "playlistId": playlist_id,
                        "position": new_position,
                        "resourceId": resource_id,
                    },
                },
            ).execute()
            return True
        except googleapiclient.errors.HttpError as e:
            print(f"      Position update failed: {e}")
            return False

    def fix_playlist_order(
        self, playlist_id: str, sort_order: str = "asc", dry_run: bool = False
    ) -> int:
        """
        Fix video ordering in playlist in-place.
        Returns number of videos that would be/were moved.
        """
        videos = self.get_playlist_videos(playlist_id)

        videos = [v for v in videos if not v["title"].startswith("Deleted video")]
        if not videos:
            print(f"[WARN] No valid videos in playlist {playlist_id}")
            return 0

        indexed = [
            (i, v, video_sort_key(v["title"], sort_order)) for i, v in enumerate(videos)
        ]

        reverse = sort_order == "desc"
        indexed.sort(key=lambda x: x[2], reverse=reverse)

        for new_pos, (orig_pos, video, _) in enumerate(indexed):
            video["target_position"] = new_pos

        moves = sum(
            1 for orig_pos, video, _ in indexed if video["target_position"] != orig_pos
        )

        if dry_run:
            return moves

        self._playlist_cache.pop(playlist_id, None)

        for target_pos in range(len(videos) - 1, -1, -1):
            videos = self.get_playlist_videos(playlist_id)

            target_title = indexed[target_pos][1]["title"]
            for video in videos:
                if video["title"] == target_title:
                    if video["position"] != target_pos:
                        self.update_playlist_item_position(
                            video["playlist_item_id"], playlist_id, target_pos
                        )
                    break

        self.clear_cache()
        return moves

    def ensure_videos_processed(
        self, video_ids: list[str], timeout: int = 300, interval: int = 10
    ) -> bool:
        """
        Wait for multiple videos to finish processing.
        Polls all videos each iteration (non-blocking per video).
        Prints progress like "10/12 videos processed".
        Returns True if all processed, False if any fail/timeout (abort).
        """
        if not video_ids:
            return True

        start = time.time()
        remaining = set(video_ids)
        failed = set()

        while time.time() - start < timeout:
            # Check all remaining videos in this iteration
            for video_id in list(remaining):
                try:
                    response = self.youtube.videos().list(
                        part="status", id=video_id
                    ).execute()
                    items = response.get("items", [])
                    if items:
                        status = items[0].get("status", {}).get("uploadStatus")
                        if status == "processed":
                            remaining.discard(video_id)
                        elif status in ("failed", "rejected"):
                            print(f"\n      [ERROR] Video {video_id}: {status}")
                            failed.add(video_id)
                            remaining.discard(video_id)
                except Exception:
                    pass  # Retry next iteration

            # Print progress
            processed_count = len(video_ids) - len(remaining) - len(failed)
            total = len(video_ids)
            print(f"    {processed_count}/{total} videos processed...", end="\r")

            # Check completion
            if not remaining:
                print(f"\n    {total}/{total} videos processed!")
                return True

            if failed:
                print(f"\n    [ABORT] {len(failed)} video(s) failed")
                return False

            time.sleep(interval)

        # Timeout reached
        print(f"\n    [ABORT] Timeout waiting for {len(remaining)} video(s)")
        return False

    def clear_cache(self):
        """Clear playlist cache to force refresh."""
        self._playlist_cache.clear()
