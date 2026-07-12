# Voice Memo Pipeline

Local tooling for Apple Voice Memos, with a clear split between the **standard Hermes skill** and a **custom automation layer** built on top of it.

## Current architecture

This stack is now intentionally layered:

1. **Standard Hermes skill** — `apple-voice-memos`
   - Reads Voice Memos metadata from Apple's read-only database
   - Prefers Apple's embedded transcript from the `.m4a` `tsrp` atom
   - Falls back to cached local Whisper transcripts when Apple has none
   - Lives in Hermes as the reusable transcript-reading skill

2. **This repo** — local fallback / plumbing
   - Keeps a portable copy of the standard skill under `codex-skill/apple-voice-memos`
   - Provides the local Whisper fallback worker in
     `codex-skill/apple-voice-memos/scripts/transcribe_missing_whisper.py`
   - Provides launchd templates for event-driven fallback transcription on macOS

3. **Custom workflow on top** — personal automation layer
   - Detects newly transcribed memos
   - Decides what action to take (reminders, research, journaling, summaries)
   - Sends iMessage summaries and writes durable logs
   - Lives outside this repo in the user's Hermes setup (`~/.hermes/scripts/` and cron)

## What this means in practice

- The **standard skill is now the source of truth** for reading Voice Memos.
- The **custom pipeline should not re-implement transcript extraction, DB access, or fallback selection**.
- Custom automation should stay focused on:
  - detecting newly actionable memos
  - state tracking
  - logging
  - deciding and executing follow-up actions

In other words:

- `apple-voice-memos` = **reader / transcript backend**
- this repo = **fallback transcription + installable plumbing**
- custom cron/scripts = **automation policy and actions**

## Repository scope

This repo is primarily for the **non-LLM local fallback path**:

- portable `apple-voice-memos` skill snapshot
- local Whisper fallback worker
- launchd wiring
- supporting export/transcription utilities

It is **not** the source of truth for the user's full voice-memo action pipeline.

## Standard skill snapshot

This repo includes a vendored copy of the standard Hermes `apple-voice-memos`
skill in:

- `codex-skill/apple-voice-memos/SKILL.md`
- `codex-skill/apple-voice-memos/scripts/voicememos.py`

That copy should track the standard skill closely so the transcript-reading layer
stays reusable and not custom-forked by accident.

## Whisper fallback flow

The fallback path works like this:

1. Load memo metadata from Apple's read-only Voice Memos database.
2. Prefer Apple's embedded transcript from the audio file's `tsrp` atom.
3. If Apple has no transcript, read a local Whisper cache from
   `~/.voicememo-whisper/transcripts/<unique_id>.txt`.
4. If the cache is missing, `transcribe_missing_whisper.py` can transcribe the
   memo locally with `faster-whisper` medium and write the cache.

The worker never writes to Apple's Voice Memos files or database.

## Event-driven macOS setup

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

## Custom automation layer (not in this repo)

The user's higher-level Hermes workflow can sit on top of the standard skill,
for example:

- `voicememo_inbox.py` to detect newly transcribed memos
- `voicememo-actions` cron job to turn memos into reminders, research, or notes
- `voicememo_log.py` to keep durable logs of transcript intake and outcomes

That layering is intentional and preferred.

## Privacy

Do not commit exported audio, transcript caches, Voice Memos databases, logs, or
`~/.voicememo-whisper` contents. The `.gitignore` excludes the repo-local audio,
transcript, and data directories.
