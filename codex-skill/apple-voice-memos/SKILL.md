---
name: apple-voice-memos
description: Read and search transcripts of the user's Apple Voice Memos on macOS. Lists recordings and extracts Apple's on-device transcripts straight from each .m4a file, falling back to cached local Whisper medium transcripts when Apple has none. Use when the user asks what a voice memo said, to summarize or search their voice memos, or to turn recent memos into notes, tasks, or summaries ("what did I record yesterday?", "read my last voice memo", "find the memo about X").
---

# Apple Voice Memos

Read and search transcripts of the user's Apple Voice Memos. On macOS 15+/iOS 18+
Voice Memos transcribes recordings on-device and embeds the transcript text
directly inside each `.m4a` file (a QuickTime `tsrp` atom). This skill reads that
text straight out of the file first. If Apple has no embedded transcript, it can
fall back to cached local Whisper medium transcripts written by the non-LLM
worker in `scripts/transcribe_missing_whisper.py`.

Recording metadata (title, date, duration) comes from the Voice Memos database,
opened read-only.

## When to Use

- User asks what a voice memo said, or to summarize / search their voice memos
- User wants recent memos turned into notes, tasks, or summaries
- "What did I record yesterday?", "read my last voice memo", "find the memo about X"

## When NOT to Use

- Transcribing arbitrary audio files (not Voice Memos) → use a transcription tool
- Recording new audio
- Memos with no embedded transcript (very old, very short, or not yet processed) —
  these show `[ ]` in `list`; the script reports when a transcript is missing

## Requirements

- **macOS only**, with Python 3 (`python3`) available.
- The process that runs this skill needs macOS **Full Disk Access** to read the
  privacy-protected Voice Memos container. Grant it under
  System Settings → Privacy & Security → Full Disk Access. The script's error
  messages say this when access is missing.

## Quick Reference

Script: `scripts/voicememos.py` (run with `python3`). All commands take `--json`.

### List recordings (newest first)

```bash
python3 scripts/voicememos.py list                      # 30 most recent
python3 scripts/voicememos.py list --limit 10
python3 scripts/voicememos.py list --with-transcript    # only ones with text
python3 scripts/voicememos.py list --search "pickwick"  # filter by title
```

`[A]` = Apple transcript, `[W]` = cached local Whisper medium transcript,
`[ ]` = none. The leading `[n]` is the index used by `transcript`.

### Read one transcript

```bash
python3 scripts/voicememos.py transcript 1              # by list index
python3 scripts/voicememos.py transcript "Recording 45" # by title search
python3 scripts/voicememos.py transcript <filename.m4a> # by filename
```

### Dump many transcripts at once (good for summarizing a batch)

```bash
python3 scripts/voicememos.py dump --limit 10 --only-transcribed
python3 scripts/voicememos.py dump --search "meeting" --json
```

## How It Works

- **Metadata:** read-only SQLite query against
  `~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings/CloudRecordings.db`
  (`ZCLOUDRECORDING` table → title, date, duration, filename).
- **Transcript:** the `.m4a` contains a `tsrp` user-data atom holding JSON
  (`attributedString.runs`); the string elements concatenated are the transcript.
- **Whisper fallback:** when no Apple transcript exists, the local cron worker
  writes text files to `~/.voicememo-whisper/transcripts/<unique_id>.txt` and the
  skill reads them as fallback only.
- Dates are stored in Cocoa epoch (2001-01-01) and converted to local time.

## Local Whisper Fallback

The fallback job is intentionally not an LLM automation. It runs local
`faster-whisper` with the medium model via `scripts/transcribe_missing_whisper.py`.
For event-driven use on macOS, install a user LaunchAgent with `WatchPaths`
pointing at:

```bash
~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings
```

It scans Voice Memos read-only, skips recordings that already have Apple's
embedded transcript, skips recordings already cached in `~/.voicememo-whisper`,
and stores the transcript plus a small JSON sidecar. It uses a lock file so a
slow run will not overlap another trigger.

## Rules

1. Prefer reading the embedded Apple transcript. The Whisper fallback is used
   only when Apple has no transcript.
2. The database is opened **read-only**; never write to Voice Memos files or DB.
3. When a requested memo has no Apple or cached Whisper transcript, say so
   plainly rather than guessing.

## Limitations

- macOS only. Requires Voice Memos to have transcribed the recording on-device
  (governed by Apple; supported languages only). Apple only writes the transcript
  after **Transcribe** is tapped in the Voice Memos app — recording alone does not
  populate it.
- Memos still syncing from iCloud may not have their `.m4a` downloaded locally yet
  (`exists: false` in `--json`).
</content>
</invoke>
