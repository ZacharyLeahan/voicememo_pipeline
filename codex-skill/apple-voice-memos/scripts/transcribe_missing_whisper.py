#!/usr/bin/env python3
"""Create local Whisper transcripts for Voice Memos missing Apple transcripts.

This worker is intended for cron/launchd. It reads the Voice Memos database and
audio files read-only, never modifies Apple's files, and stores fallback
transcripts in ~/.voicememo-whisper/transcripts keyed by the Voice Memos
unique_id. The Codex apple-voice-memos skill reads the same cache.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import sys
import time
from pathlib import Path

from voicememos import (
    WHISPER_TRANSCRIPTS_DIR,
    best_transcript,
    extract_transcript,
    load_recordings,
    whisper_transcript_path,
)

SUPPORTED_AUDIO_SUFFIXES = {".m4a", ".mp3", ".mp4", ".mpeg", ".mpga", ".wav", ".webm", ".qta"}
STATE_DIR = Path(os.path.expanduser("~/.voicememo-whisper"))
LOG_PATH = STATE_DIR / "transcribe.log"
LOCK_PATH = STATE_DIR / "transcribe.lock"


def log(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"{stamp} {message}"
    print(line, file=sys.stderr)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def metadata_path(transcript_path: Path) -> Path:
    return transcript_path.with_suffix(".json")


def failure_path(transcript_path: Path) -> Path:
    return transcript_path.with_suffix(".failed.json")


def pending_recordings(*, force: bool) -> list[dict]:
    recs = load_recordings()
    pending: list[dict] = []
    for rec in recs:
        if not rec["exists"]:
            continue
        audio_path = Path(rec["path"])
        if audio_path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
            continue
        if not force and extract_transcript(audio_path):
            continue
        if not force and best_transcript(rec)[0]:
            continue
        if not force and failure_path(whisper_transcript_path(rec)).exists():
            continue
        pending.append(rec)
    return pending


def transcribe_recordings(args: argparse.Namespace) -> int:
    pending = pending_recordings(force=args.force)
    if args.max_files:
        pending = pending[: args.max_files]

    if args.dry_run:
        for rec in pending:
            print(f"{rec['date_human']} {rec['title']} ({rec['filename']})")
        return 0

    if not pending:
        log("no missing Voice Memo transcripts")
        return 0

    from faster_whisper import WhisperModel

    log(f"loading faster-whisper model={args.model}")
    model = WhisperModel(
        args.model,
        device=args.device,
        compute_type=args.compute_type,
        local_files_only=True,
    )

    WHISPER_TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for rec in pending:
        audio_path = Path(rec["path"])
        out_path = whisper_transcript_path(rec)
        tmp_path = out_path.with_suffix(".txt.tmp")
        lang = args.language or None
        kwargs: dict[str, object] = {}
        if lang:
            kwargs["language"] = lang

        log(f"transcribing {rec['title']!r} {rec['filename']}")
        try:
            segments, info = model.transcribe(str(audio_path), **kwargs)
            text = "".join(segment.text for segment in segments).strip()
            if not text:
                raise RuntimeError("Whisper returned an empty transcript")
            tmp_path.write_text(text + "\n", encoding="utf-8")
            tmp_path.replace(out_path)
            metadata_path(out_path).write_text(
                json.dumps(
                    {
                        "title": rec["title"],
                        "filename": rec["filename"],
                        "path": rec["path"],
                        "date": rec["date"],
                        "duration_sec": rec["duration_sec"],
                        "unique_id": rec["unique_id"],
                        "transcript_source": "whisper-medium",
                        "backend": "faster_whisper",
                        "model": args.model,
                        "language": getattr(info, "language", None),
                        "language_probability": getattr(info, "language_probability", None),
                        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            failed_path = failure_path(out_path)
            if failed_path.exists():
                failed_path.unlink()
            count += 1
            log(f"wrote {out_path}")
        except Exception as exc:
            log(f"failed {rec['title']!r} {rec['filename']}: {exc}")
            failure_path(out_path).write_text(
                json.dumps(
                    {
                        "title": rec["title"],
                        "filename": rec["filename"],
                        "path": rec["path"],
                        "date": rec["date"],
                        "duration_sec": rec["duration_sec"],
                        "unique_id": rec["unique_id"],
                        "backend": "faster_whisper",
                        "model": args.model,
                        "error": str(exc),
                        "failed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            continue

    log(f"done transcribed={count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Transcribe Voice Memos missing Apple transcripts with local Whisper."
    )
    parser.add_argument("--model", default="medium", help="faster-whisper model name")
    parser.add_argument("--language", default="en", help="ISO-639-1 language, or empty for auto")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--compute-type", default="default")
    parser.add_argument("--max-files", type=int, default=0, help="limit files per run; 0 means all")
    parser.add_argument(
        "--settle-seconds",
        type=int,
        default=0,
        help="wait this many seconds after taking the lock before scanning",
    )
    parser.add_argument("--force", action="store_true", help="retranscribe even if cache exists")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w", encoding="utf-8") as lock_fh:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("another transcribe_missing_whisper.py run is active; exiting")
            return 0
        if args.settle_seconds > 0:
            log(f"waiting {args.settle_seconds}s for Voice Memos writes to settle")
            time.sleep(args.settle_seconds)
        return transcribe_recordings(args)


if __name__ == "__main__":
    raise SystemExit(main())
