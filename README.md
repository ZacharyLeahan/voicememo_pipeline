# Voice Memo Pipeline

Local tooling for exporting and transcribing Apple Voice Memos.

## Codex Skill + Whisper Fallback

This repo includes a portable copy of the Codex `apple-voice-memos` skill in
`codex-skill/apple-voice-memos`.

The skill reads Voice Memos in this order:

1. Load memo metadata from Apple's read-only Voice Memos database.
2. Prefer Apple's embedded transcript from the audio file's `tsrp` atom.
3. If Apple has no transcript, read a local Whisper cache from
   `~/.voicememo-whisper/transcripts/<unique_id>.txt`.
4. If the cache is missing, `transcribe_missing_whisper.py` can transcribe the
   memo locally with `faster-whisper` medium and write the cache.

The worker never writes to Apple's Voice Memos files or database.

## Event-Driven macOS Setup

Use the templates as installation inputs:

- `codex-skill/apple-voice-memos/scripts/run_whisper_launchd.sh.template`
- `launchd/com.example.voicememo-whisper.plist.template`

Replace these placeholders:

- `__HOME__`: your home directory
- `__PYTHON__`: Python executable from a venv with `faster-whisper`
- `__SKILL_DIR__`: installed skill directory
- `__LABEL__`: a unique LaunchAgent label, for example
  `com.example.voicememo-whisper`

Install the plist into `~/Library/LaunchAgents/`, then load it with:

```bash
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.example.voicememo-whisper.plist
```

The LaunchAgent watches:

```text
~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings
```

When Voice Memos writes to that folder, `launchd` runs the worker once. The
wrapper waits 20 seconds for writes to settle, scans once, transcribes missing
fallbacks, then exits.

macOS Full Disk Access is required for the shell/Python path that launchd runs.

## Privacy

Do not commit exported audio, transcript caches, Voice Memos databases, logs, or
`~/.voicememo-whisper` contents. The `.gitignore` excludes the repo-local audio,
transcript, and data directories.
