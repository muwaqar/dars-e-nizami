#!/usr/bin/env python3
"""
cutter.py - Cut Zoom recordings into individual class segments.

Usage:
    python3 cutter.py input.mp4                      # Interactive mode
    python3 cutter.py input.mp4 --path Section-F/2026-04-11  # With destination path
    python3 cutter.py input.mp4 --dry-run          # Preview without cutting
    python3 cutter.py input.mp4 --overwrite         # Overwrite existing files
    python3 cutter.py input.mp4 --config path/to/config.json
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import questionary


def load_config(config_path: str | Path) -> dict:
    config_path = Path(config_path).expanduser().resolve()
    with open(config_path) as f:
        return json.load(f)


def get_duration(video_path: str) -> str:
    """Get video duration using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    seconds = float(result.stdout.strip())
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def get_duration_seconds(time_str: str) -> float:
    """Convert HH:MM:SS to seconds."""
    parts = time_str.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    else:
        return float(time_str)


def add_minutes(time_str: str, minutes: int) -> str:
    """Add minutes to a HH:MM:SS time string."""
    seconds = get_duration_seconds(time_str) + (minutes * 60)
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}"


def prompt_choice(prompt_text: str, options: list[str]) -> int | None:
    """Interactive arrow key selection menu."""
    if not options:
        return None
    choice = questionary.select(
        prompt_text,
        choices=options,
        pointer=">",
    ).ask()
    if choice is None:
        return None
    return options.index(choice) + 1


def prompt_time(prompt_text: str, default: str = None) -> str:
    """Prompt for time in HH:MM:SS format."""
    while True:
        kwargs = {
            "qmark": ">",
            "validate": lambda x: _validate_time(x) is not None,
        }
        if default:
            kwargs["default"] = default
            prompt_with_default = f"{prompt_text} ({default})"
        else:
            prompt_with_default = prompt_text

        time_val = questionary.text(prompt_with_default, **kwargs).ask()

        if not time_val and default:
            time_val = default
        try:
            get_duration_seconds(time_val)
            return time_val
        except (ValueError, ZeroDivisionError, AttributeError):
            print("Invalid format. Use HH:MM:SS")


def _validate_time(time_str: str) -> float | None:
    """Validate time string and return seconds or None."""
    if not time_str:
        return None
    try:
        return get_duration_seconds(time_str)
    except (ValueError, ZeroDivisionError):
        return None


def get_subjects(config: dict) -> dict:
    """Get subjects from config."""
    return config["subjects"]


def get_recordings_path(config_path: Path) -> Path:
    """Get recordings path from config location."""
    config_dir = config_path.parent
    config = load_config(config_path)
    recordings = config.get("recordings_path", "Recordings")
    return (config_dir / recordings).expanduser().resolve()


def check_ffmpeg():
    """Check if ffmpeg is installed."""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        if result.returncode != 0:
            raise FileNotFoundError()
    except FileNotFoundError:
        print("Error: ffmpeg not found.")
        print("Install with: brew install ffmpeg")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Cut Zoom recordings into class segments"
    )
    parser.add_argument("input", help="Input video file")
    parser.add_argument("--path", help="Destination path (e.g., Section-F/2026-04-11)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without cutting"
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing files"
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Config file path (default: config.json)",
    )
    args = parser.parse_args()

    args.config = Path(args.config).expanduser().resolve()

    check_ffmpeg()

    input_file = Path(args.input)
    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)

    print("=" * 60)
    print("cutter")
    print("=" * 60)
    print(f"\nProcessing: {input_file.name}")

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"Error: Config file not found: {args.config}")
        sys.exit(1)

    recordings_path = get_recordings_path(args.config)

    duration = get_duration(str(input_file))
    print(f"Duration: {duration}")

    subjects = get_subjects(config)
    subject_names = list(subjects.keys())

    default_path = args.path
    if not default_path:
        today = datetime.now().strftime("%Y-%m-%d")
        default_path = today

    segments = []
    last_end = "00:00:00"
    print("\n" + "=" * 60)
    print("Enter segments")
    print("=" * 60)

    while True:
        print(f"\n--- Segment {len(segments) + 1} ---")

        start_time = prompt_time("Start time (HH:MM:SS)", last_end)
        end_time = prompt_time("End time (HH:MM:SS)", add_minutes(start_time, 30))

        start_secs = get_duration_seconds(start_time)
        end_secs = get_duration_seconds(end_time)
        if end_secs <= start_secs:
            print("Error: End time must be after start time")
            continue

        idx = prompt_choice("Select subject", subject_names)
        if idx is None:
            continue
        selected_subject = subject_names[idx - 1]
        parts = subjects[selected_subject]["parts"]

        if parts == 1:
            selected_part = 1
        else:
            part_options = [str(i) for i in range(1, parts + 1)]
            part_idx = prompt_choice("Select part", part_options)
            if part_idx is None:
                continue
            selected_part = part_idx

        filename = f"{len(segments) + 1}. {selected_subject} {selected_part}.mp4"

        print(f"\n  {start_time} - {end_time} → {filename}")

        confirm = questionary.select(
            "Action",
            choices=["Accept", "Edit", "Skip", "Cancel"],
            pointer=">",
        ).ask()

        if confirm == "Accept":
            segments.append(
                {
                    "start": start_time,
                    "end": end_time,
                    "subject": selected_subject,
                    "part": selected_part,
                    "filename": filename,
                }
            )
            last_end = end_time
        elif confirm == "Edit":
            continue
        elif confirm == "Skip":
            continue
        elif confirm == "Cancel":
            print("\nCutting cancelled.")
            sys.exit(0)

        more = questionary.confirm("Add another segment?").ask()
        if not more:
            break

    if not segments:
        print("No segments entered.")
        sys.exit(0)

    if not args.path:
        path_prompt = questionary.text(
            f"Destination path (e.g., Section-F/{default_path})",
            default=default_path,
        ).ask()
    else:
        path_prompt = args.path

    dest_dir = recordings_path / path_prompt.replace("/", os.sep)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Destination: {dest_dir}")
    print(f"Segments: {len(segments)}")
    for seg in segments:
        print(f"  {seg['start']} - {seg['end']} → {seg['filename']}")

    if args.dry_run:
        print("\n[DRY-RUN] No files were created.")
        sys.exit(0)

    confirm = questionary.confirm("Proceed with cutting?").ask()
    if not confirm:
        print("Cancelled.")
        sys.exit(0)

    dest_dir.mkdir(parents=True, exist_ok=True)

    for seg in segments:
        output_file = dest_dir / seg["filename"]
        if output_file.exists() and not args.overwrite:
            print(f"\n[WARN] File exists: {output_file}")
            overwrite = questionary.confirm("Overwrite?").ask()
            if not overwrite:
                print("  Skipping.")
                continue

        start_secs = get_duration_seconds(seg["start"])
        end_secs = get_duration_seconds(seg["end"])

        print(f"\nCutting: {seg['start']} - {seg['end']} → {seg['filename']}")

        cmd = [
            "ffmpeg",
            "-y" if args.overwrite else "-n",
            "-ss",
            str(start_secs),
            "-to",
            str(end_secs),
            "-i",
            str(input_file),
            "-c",
            "copy",
            str(output_file),
        ]

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            print(f"  [ERROR] ffmpeg failed")
            if result.stderr:
                print(f"  {result.stderr.decode()[:500]}")
        else:
            print(f"  [OK] Created: {output_file.name}")

    print("\n" + "=" * 60)
    print("Done")
    print("=" * 60)


if __name__ == "__main__":
    main()
