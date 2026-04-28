#!/usr/bin/env python3
"""
syncer.py - Upload recordings to YouTube and organize into playlists.

Usage:
    python3 syncer.py                     # Sync all recordings
    python3 syncer.py --path Section-F   # Sync specific path
    python3 syncer.py --path Section-F/2026-04-11  # Sync specific path
    python3 syncer.py --dry-run          # Preview mode
    python3 syncer.py --verbose          # Show all video status
    python3 syncer.py --re-authenticate  # Force fresh OAuth authentication
    python3 syncer.py --config path/to/config.json     # Use custom config
    python3 syncer.py --credentials path/to/secrets.json  # Use custom credentials
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def find_date_in_path(path: Path) -> str | None:
    for part in reversed(path.parts):
        if DATE_PATTERN.match(part):
            return part
    filename_without_ext = path.name.removesuffix(".mp4")
    match = DATE_PATTERN.match(filename_without_ext)
    if match:
        return match.group(0)
    return None


def get_video_files(
    recordings_path: Path, path_filter: str = None
) -> list[tuple[Path, str]]:
    if path_filter:
        pattern = f"**/{path_filter}/**/*.mp4"
    else:
        pattern = "**/*.mp4"

    matches = list(recordings_path.glob(pattern))

    results = []
    for mp4 in matches:
        date_str = find_date_in_path(mp4)
        if date_str:
            results.append((mp4, date_str))
        else:
            print(f"  [WARN] No date in path, skipping: {mp4}")

    return sorted(results, key=lambda x: (x[1], x[0].name))


def sync_group(
    files: list[tuple[Path, str]],
    client,
    dry_run: bool,
    verbose: bool = False,
) -> tuple[dict, list[str]]:
    """Sync videos. Returns (stats, interacted_video_ids)."""
    from config import (
        find_playlist_for_file,
        get_yt_playlist_id,
        get_yt_video_prefix,
        get_yt_playlist_sort,
        get_part_from_filename,
        get_serial_from_filename,
        generate_title,
    )

    if not files:
        return {
            "total": 0,
            "uploaded": 0,
            "added": 0,
            "skipped": 0,
            "errors": 0,
            "would_upload": 0,
        }, []

    stats = {
        "total": len(files),
        "uploaded": 0,
        "added": 0,
        "skipped": 0,
        "errors": 0,
        "would_upload": 0,
    }
    interacted_ids = []

    # Group files by (playlist_filename_key, part, date) to detect multiples
    from collections import defaultdict
    groups = defaultdict(list)
    for file_path, date_str in files:
        filename = file_path.name
        playlist = find_playlist_for_file(filename)
        if playlist is None:
            continue
        part = get_part_from_filename(filename)
        filename_key = playlist.get("filename_key", "")
        groups[(filename_key, part, date_str)].append((file_path, date_str))

    # Build sequence info for files in groups with multiple entries
    sequence_map = {}  # (file_path, date_str) -> (sequence, total)
    for (filename_key, part, date_str), group_files in groups.items():
        if len(group_files) > 1:
            # Sort by serial number
            group_files_sorted = sorted(
                group_files,
                key=lambda x: (get_serial_from_filename(x[0]) or 0, x[0].name)
            )
            total = len(group_files_sorted)
            for idx, (file_path, ds) in enumerate(group_files_sorted, start=1):
                sequence_map[(file_path, ds)] = (idx, total)

    for file_path, date_str in files:
        filename = file_path.name

        playlist = find_playlist_for_file(filename)
        if playlist is None:
            print(f"  [ERROR] {filename}: No matching playlist found, skipping")
            stats["errors"] += 1
            continue

        playlist_id = get_yt_playlist_id(playlist)
        yt_prefix = get_yt_video_prefix(playlist)
        sort_order = get_yt_playlist_sort(playlist)
        part = get_part_from_filename(filename)

        # Get sequence info if this file is part of a multiple-class group
        seq_info = sequence_map.get((file_path, date_str))
        sequence = seq_info[0] if seq_info else None
        total = seq_info[1] if seq_info else None

        title = generate_title(yt_prefix, part, date_str, sequence, total)

        if verbose:
            print(f"\nProcessing: {filename}")
            print(f"  → Title: {title}")
            print(f"  → Playlist: {yt_prefix}")

        if client.video_exists_in_playlist(playlist_id, title):
            if verbose:
                print(f"  [INFO] Already exists in playlist, checking processing status...")
            # Still add to interacted_ids so processing check waits for it
            video = client.find_video_on_youtube(title)
            if video:
                interacted_ids.append(video["video_id"])
            stats["skipped"] += 1
            continue

        position = client.calculate_position(
            playlist_id, yt_prefix, part, date_str, sort_order
        )

        if dry_run:
            print(f"  {filename} → {title} [would upload, position {position + 1}]")
            stats["would_upload"] += 1
            continue

        print(f"  {filename} → {title}")

        video = client.find_video_on_youtube(title)
        if video:
            print(f"    Found on YouTube, adding to playlist...")
            video_id = video["video_id"]
            interacted_ids.append(video_id)
        else:
            video_id = client.upload_video(str(file_path), title)
            if video_id:
                interacted_ids.append(video_id)

        if not video_id:
            print(f"    [ERROR] Upload failed after retries")
            stats["errors"] += 1
            continue

        if video:
            action = "ADD"
        else:
            action = "UPLOAD"

        if verbose:
            print(f"    [PLAYLIST] Adding at position {position + 1}...")

        if client.add_to_playlist(playlist_id, video_id, position):
            if verbose:
                print(f"    [SUCCESS] Added to playlist")
            if action == "UPLOAD":
                stats["uploaded"] += 1
            else:
                stats["added"] += 1
        else:
            if verbose:
                print(f"    [ERROR] Failed to add to playlist")
            stats["errors"] += 1

    return stats, interacted_ids


def resolve_credentials(credentials_path: str = None) -> str:
    """
    Resolve credentials file path.
    Priority: --credentials flag > ./client_secret.json > error
    """
    if credentials_path:
        path = Path(credentials_path).expanduser().resolve()
        if path.exists():
            return str(path)
        raise FileNotFoundError(f"Credentials file not found: {credentials_path}")

    cwd_secret = Path.cwd() / "client_secret.json"
    if cwd_secret.exists():
        return str(cwd_secret)

    raise FileNotFoundError(
        "client_secret.json not found in current directory. "
        "Use --credentials to specify a custom path."
    )


def main():
    from config import (
        load_config,
        get_playlists,
        get_recordings_path,
        get_yt_video_prefix,
        get_yt_playlist_id,
        get_yt_playlist_sort,
    )

    parser = argparse.ArgumentParser(description="Sync recordings to YouTube")
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config file (default: config.json)",
    )
    parser.add_argument(
        "--credentials",
        help="Path to client_secret.json (default: ./client_secret.json)",
    )
    parser.add_argument(
        "--path",
        help="Filter recordings by path (e.g., 'Section-F', 'Section-F/2026-04-11')",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without uploading"
    )
    parser.add_argument("--verbose", action="store_true", help="Show all video status")
    parser.add_argument(
        "--re-authenticate",
        action="store_true",
        help="Force fresh OAuth authentication",
    )
    args = parser.parse_args()

    print("=" * 60)
    if args.dry_run:
        print("DRY-RUN MODE - No changes will be made")
    print("yt-sync")
    print("=" * 60)

    print(f"\nLoading config from: {args.config}")
    try:
        load_config(args.config)
    except FileNotFoundError:
        print(f"Config file not found: {args.config}")
        sys.exit(1)

    credentials_path = resolve_credentials(args.credentials)

    from youtube_client import YouTubeClient

    print("\nAuthenticating with YouTube...")
    try:
        client = YouTubeClient(
            credentials_file=credentials_path,
            re_authenticate=args.re_authenticate,
        )
    except Exception as e:
        print(f"Authentication failed: {e}")
        sys.exit(1)

    playlists = get_playlists()
    recordings_path = get_recordings_path()

    video_files = get_video_files(recordings_path, args.path)

    groups = defaultdict(list)
    for mp4_path, date_str in video_files:
        groups[mp4_path.parent].append((mp4_path, date_str))

    total_stats = {
        "total": 0,
        "uploaded": 0,
        "added": 0,
        "skipped": 0,
        "errors": 0,
        "would_upload": 0,
    }

    all_interacted_ids = []

    for dir_path, files in sorted(groups.items()):
        dir_display = dir_path.relative_to(recordings_path)
        print(f"\n=== Syncing {dir_display} ===")
        stats, interacted_ids = sync_group(files, client, args.dry_run, args.verbose)
        for k in total_stats:
            total_stats[k] += stats[k]
        all_interacted_ids.extend(interacted_ids)

    # Wait for video processing, abort if failed
    if not args.dry_run and all_interacted_ids:
        print("\n" + "=" * 60)
        print("=== Waiting for Video Processing ===")
        print("=" * 60)
        success = client.ensure_videos_processed(all_interacted_ids)

        if not success:
            print("\n    [ABORT] Skipping playlist ordering")
            print("\n" + "=" * 60)
            print("=== Summary ===")
            print("=" * 60)
            print(f"Total:         {total_stats['total']:>5}")
            print(f"Uploaded:      {total_stats['uploaded']:>5}")
            print(f"Added (exist): {total_stats['added']:>5}")
            print(f"Skipped:       {total_stats['skipped']:>5}")
            print(f"Errors:        {total_stats['errors']:>5}")
            return

    print("\n" + "=" * 60)
    print("=== Fixing playlist ordering ===")
    print("=" * 60)
    for playlist in playlists:
        playlist_id = get_yt_playlist_id(playlist)
        yt_prefix = get_yt_video_prefix(playlist)
        sort_order = get_yt_playlist_sort(playlist)
        moved = client.fix_playlist_order(
            playlist_id, sort_order=sort_order, dry_run=args.dry_run
        )
        if args.dry_run:
            print(f"  [ORDER] {yt_prefix}: Would fix {moved} videos")
        else:
            print(f"  [ORDER] {yt_prefix}: Fixed {moved} videos")

    print("\n" + "=" * 60)
    print("=== Summary ===")
    print("=" * 60)
    print(f"Total:         {total_stats['total']:>5}")
    if args.dry_run:
        print(f"Would upload:  {total_stats['would_upload']:>5}")
        print(f"Would skip:    {total_stats['skipped']:>5}")
        print(f"Would error:   {total_stats['errors']:>5}")
    else:
        print(f"Uploaded:      {total_stats['uploaded']:>5}")
        print(f"Added (exist): {total_stats['added']:>5}")
        print(f"Skipped:       {total_stats['skipped']:>5}")
        print(f"Errors:        {total_stats['errors']:>5}")


if __name__ == "__main__":
    main()
