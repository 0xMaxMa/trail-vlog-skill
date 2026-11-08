# trail-vlog (Claude Code skill)

Turns raw action-cam trail footage (+ optional Garmin .FIT) into an edited 8–10 min YouTube vlog:
dead-air cutting, Thai punchline captions, ElevenLabs music per section, live Garmin HUD + route map,
chapter cards, meme stickers, poster-style thumbnail, YouTube `.srt`, and small LINE-sized parts.

- `SKILL.md` — workflow the agent follows
- `CHECKLIST.md` — what to prepare before/after a run
- `scripts/` — setup, ingest, stt, garmin, build (render), srt, cover, image, music, line_split
- `templates/` — `project.json` + `edl.py` starters
- `examples/nongho-2026-11-08/` — a complete real edit

## Install
Claude Code: `ln -s "$PWD" ~/.claude/skills/trail-vlog`
claude-gateway: `ln -s "$PWD" ~/.claude-gateway/shared-skills/trail-vlog` (gateway syncs it to every agent)

Needs: ffmpeg with libass/freetype, python3. Keys via env only: `XI_KEY` (ElevenLabs), `GETPOD_KEY` (images).
