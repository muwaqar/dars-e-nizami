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
    playlists: dict = None,
    parse_filename_fn=None,
    generate_title_fn=None,
):
    """Sync all videos for a group of files in the same directory."""
    from config import parse_filename, generate_title

    if playlists is None:
        from config import get_playlists

        playlists = get_playlists()
    if parse_filename_fn is None:
        parse_filename_fn = parse_filename
    if generate_title_fn is None:
        generate_title_fn = generate_title

    if not files:
        return {"total": 0, "uploaded": 0, "added": 0, "skipped": 0, "errors": 0}

    date_str = files[0][1]
    file_paths = [f[0] for f in files]

    stats = {
        "total": len(file_paths),
        "uploaded": 0,
        "added": 0,
        "skipped": 0,
        "errors": 0,
    }

    for file_path in file_paths:
        filename = file_path.name

        try:
            subject, part = parse_filename_fn(filename)
        except ValueError as e:
            print(f"  [ERROR] {filename}: {e}")
            stats["errors"] += 1
            continue

        if subject not in playlists:
            print(f"  [WARN] {filename}: Unknown subject '{subject}', skipping")
            stats["skipped"] += 1
            continue

        playlist_id = playlists[subject]
        title = generate_title_fn(subject, part, date_str)

        if verbose:
            print(f"\nProcessing: {filename}")
            print(f"  → Title: {title}")
            print(f"  → Playlist: {subject}")

        if client.video_exists_in_playlist(playlist_id, title):
            if verbose:
                print(f"  [INFO] Skipping (already exists in playlist)")
            stats["skipped"] += 1
            continue

        position = client.calculate_position(playlist_id, subject, part, date_str)

        if dry_run:
            video = client.find_video_on_youtube(title)
            if video:
                print(
                    f"  {filename} → {title} [exists on YT, would add at position {position + 1}]"
                )
            else:
                print(f"  {filename} → {title} [would upload, position {position + 1}]")
            stats["skipped"] += 1
            continue

        print(f"  {filename} → {title}")

        video = client.find_video_on_youtube(title)
        if video:
            print(f"    Found on YouTube, adding to playlist...")
            video_id = video["video_id"]
        else:
            video_id = client.upload_video(str(file_path), title)

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

    return stats


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
    from config import load_config, get_playlists, get_recordings_path

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

    total_stats = {"total": 0, "uploaded": 0, "added": 0, "skipped": 0, "errors": 0}

    for dir_path, files in sorted(groups.items()):
        dir_display = dir_path.relative_to(recordings_path)
        print(f"\n=== Syncing {dir_display} ===")
        stats = sync_group(files, client, args.dry_run, args.verbose, playlists)
        for k in total_stats:
            total_stats[k] += stats[k]

    print("\n" + "=" * 60)
    print("=== Fixing playlist ordering ===")
    print("=" * 60)
    for subject, playlist_id in playlists.items():
        moved = client.fix_playlist_order(playlist_id, dry_run=args.dry_run)
        if args.dry_run:
            print(f"  [ORDER] {subject}: Would fix {moved} videos")
        else:
            print(f"  [ORDER] {subject}: Fixed {moved} videos")

    print("\n" + "=" * 60)
    print("=== Summary ===")
    print("=" * 60)
    print(f"Total:    {total_stats['total']}")
    if args.dry_run:
        would_upload_or_add = (
            total_stats["total"] - total_stats["skipped"] - total_stats["errors"]
        )
        print(f"Would upload or add: {would_upload_or_add}")
        print(f"Would skip:   {total_stats['skipped']}")
        print(f"Would error:  {total_stats['errors']}")
    else:
        print(f"Uploaded: {total_stats['uploaded']}")
        print(f"Added (existing): {total_stats['added']}")
        print(f"Skipped:  {total_stats['skipped']}")
        print(f"Errors:   {total_stats['errors']}")


if __name__ == "__main__":
    main()
