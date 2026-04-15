#!/usr/bin/env python3
"""
syncer.py - Upload recordings to YouTube and organize into playlists.

Usage:
    python syncer.py                           # Sync all sections, all dates
    python syncer.py --section F              # Sync Section F only
    python syncer.py --section H              # Sync Section H only
    python syncer.py --date 2026-04-11        # Sync specific date
    python syncer.py --dry-run                # Preview mode
    python syncer.py --verbose                 # Show all video status
    python syncer.py --re-authenticate        # Force fresh OAuth authentication
    python syncer.py --config path/to/config.json     # Use custom config file
    python syncer.py --credentials path/to/client_secret.json  # Use custom credentials
    python syncer.py --section F --dry-run     # Combine options
"""

import argparse
import os
import sys
from pathlib import Path


def find_default_config() -> str:
    """Find default config.json in Recordings parent directory."""
    cwd = Path.cwd()
    recordings_candidate = cwd / "Recordings"
    if recordings_candidate.exists() and recordings_candidate.is_dir():
        config_candidate = cwd / "config.json"
        if config_candidate.exists():
            return str(config_candidate)
    config_candidate = cwd / "config.json"
    if config_candidate.exists():
        return str(config_candidate)
    parent_recordings = cwd.parent / "Recordings"
    if parent_recordings.exists() and parent_recordings.is_dir():
        config_candidate = cwd.parent / "config.json"
        if config_candidate.exists():
            return str(config_candidate)
    return "config.json"


def get_dates_for_section(section: str, recordings_path: Path) -> list[Path]:
    """Get all date directories for a section."""
    section_path = recordings_path / f"Section-{section}"
    if not section_path.exists():
        return []
    return sorted([d for d in section_path.iterdir() if d.is_dir()])


def get_mp4_files(date_path: Path) -> list[Path]:
    """Get all MP4 files in a date directory."""
    return sorted([f for f in date_path.iterdir() if f.suffix == ".mp4"])


def sync_date(
    section: str,
    date_path: Path,
    client,
    dry_run: bool,
    verbose: bool = False,
    playlists: dict = None,
    parse_filename_fn=None,
    generate_title_fn=None,
):
    """Sync all videos for a specific date."""
    from config import parse_filename, generate_title

    if playlists is None:
        from config import get_playlists

        playlists = get_playlists()
    if parse_filename_fn is None:
        parse_filename_fn = parse_filename
    if generate_title_fn is None:
        generate_title_fn = generate_title

    date_str = date_path.name
    files = get_mp4_files(date_path)

    if not files:
        return {"total": 0, "uploaded": 0, "added": 0, "skipped": 0, "errors": 0}

    print(f"\n=== Syncing Section-{section}, {date_str} ===")

    stats = {"total": len(files), "uploaded": 0, "added": 0, "skipped": 0, "errors": 0}

    for file_path in files:
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

    default_config = find_default_config()

    parser = argparse.ArgumentParser(description="Sync recordings to YouTube")
    parser.add_argument(
        "--config",
        default=default_config,
        help=f"Path to config file (default: {default_config})",
    )
    parser.add_argument(
        "--credentials",
        help="Path to client_secret.json (default: ./client_secret.json)",
    )
    parser.add_argument(
        "--section", choices=["F", "H"], help="Section to sync (F or H)"
    )
    parser.add_argument("--date", help="Specific date to sync (YYYY-MM-DD)")
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
    print("Dars-e-Nizami Syncer")
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

    sections = [args.section] if args.section else ["F", "H"]

    total_stats = {"total": 0, "uploaded": 0, "added": 0, "skipped": 0, "errors": 0}

    for section in sections:
        section_path = recordings_path / f"Section-{section}"
        if not section_path.exists():
            print(f"\nSection {section} not found at {section_path}")
            continue

        dates = get_dates_for_section(section, recordings_path)

        if args.date:
            date_path = section_path / args.date
            if date_path.exists() and date_path.is_dir():
                stats = sync_date(
                    section, date_path, client, args.dry_run, args.verbose, playlists
                )
                for k in total_stats:
                    total_stats[k] += stats[k]
            else:
                print(f"\nDate {args.date} not found in Section {section}")
        else:
            for date_path in dates:
                stats = sync_date(
                    section, date_path, client, args.dry_run, args.verbose, playlists
                )
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
