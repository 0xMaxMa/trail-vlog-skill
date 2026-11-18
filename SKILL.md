---
name: trail-vlog
description: Edit raw action-cam footage (DJI etc.) from a trail run/hike into a fun 8–10 min YouTube vlog — cut dead air, Thai punchline captions, AI music per section, live Garmin data HUD (HR/grade/altitude/km + route map), chapter cards, meme stickers, poster-style thumbnail, YouTube .srt, and small parts for LINE. Use when the user brings trail/race footage (+ optional Garmin .FIT) and wants an edited vlog.
argument-hint: <footage folder> [project folder]
---

# trail-vlog

Turn a folder of raw clips into an edited vlog, the way it was done for the 2026-11-08 Nong Ho → Khun Chang Khian warmup
(see `examples/nongho-2026-11-08/` — a complete real `edl.py` + `project.json`). Scripts live in `scripts/` next to this file;
call them by absolute path. **Everything for one job stays inside one project folder** (user preference).

Read `CHECKLIST.md` first and get the inputs from the user. Talk to the user in Thai.

## Project layout (`setup.sh` creates it)
```
<project>/raw/       original clips (copied off the SD card; never edit or delete)
<project>/garmin/    .FIT + records.json            <project>/music/   generated tracks + sfx
<project>/sprites/   PNG stickers/logos             <project>/cover/   thumbnails + AI art
<project>/fonts/     Kanit                          <project>/output/  final mp4, srt, LINE parts
<project>/work/      venv, audio, stt, frames, sheets, proxy, seg_*, edl.py, test/
<project>/project.json   titles, stats, clock offset, theme, stickers, cover text, srt fixes
```

## Workflow (do the steps in order; show the user results at each ✋)

1. **Setup** — `bash scripts/setup.sh <project>`; copy clips with `rsync -a --include='*.MP4' --include='*.MOV' --exclude='*' <sd>/ <project>/raw/`
   (skip .LRF proxies). Check nothing is still copying (sizes stable over 5 s) and every clip opens with ffprobe.
2. **Ingest** — `bash scripts/ingest.sh <project>` (audio, 960×540 proxies, frames every 4 s, 6×5 contact sheets; prints sheet→clip map).
3. **Transcribe** — `XI_KEY=… work/venv/bin/python -I scripts/stt.py <project> tha` → `work/transcript.txt` (per-clip, timestamped).
   Read the whole transcript. Scribe hears "Claude Code" as คอสโค้ด etc. — collect fixes for `srt_fixes`.
   **Proper names (places, temples, people, villages) from STT are guesses** — PST100: บ้านปง→"บ้านโป่ง", วัดโลหะปราสาท→
   "พระธาตุศรีสองรัก", ป๊อย→"ป๋อย". Never put an STT-derived name on screen as fact: check the official race map/station list,
   or list the names you plan to show and ask the user once.
4. **Look** — Read contact sheets (`work/sheets/sNN.jpg`) for the clips you might use; skip obviously unusable ones. Don't read all of them blindly.
5. **Garmin** (if .FIT) — `work/venv/bin/python -I scripts/garmin.py <project> <file.fit> 7` → records.json, summary, km splits, stops.
   **Clock offset**: DJI file names carry the *camera* clock, which can be wrong by minutes. Align Garmin stops (lunch, checkpoints,
   finish) with what the transcript/frames show, and/or have the user film a 3 s clip while noting real time. Put the result in
   `camera_offset_s` (positive = camera fast). If the watch was started late, set `prestart_km`. Verify by spot-checking HUD numbers
   against a known moment (e.g. altitude said on camera).
6. ✋ **Outline** — first ask the user for **the story in their words** (the low points, turning points, who they met,
   what they want emphasised and what they do NOT want shown) — PST100's best beats (legs gone at KM 55, A5 doubt, Last Man
   crawl, legs revived at A6, the fall before the finish) came from the user, not the transcript.
   Then propose a Thai outline table: sections, length, which clips, jokes kept, music mood, graphics. Target **8–10 min**
   for a day hike; a 100 km race ended at ~30 min with one chapter per station leg,
   keep only ~15–20 % of raw. Structure that worked: hook (best line, 5–10 s, no music) → fast montage at 2.5–3× ending on the title
   card → intro/gang → chapters following the day (rain/climb/views/village/food/descent…) → finish + summary card + sign-off.
   Wait for approval.
7. **EDL** — write `work/edl.py` (format documented in `templates/edl_template.py`). Use `scripts/words.py <project> <clip> a b`
   to place cuts on word boundaries; never cut a punchline or an answer mid-sentence (user complaint: "ตัดเร็วไป ยังพูดไม่จบ",
   7 times in one PST100 review). `build.py` now **snaps speech pieces to whole phrases** (STT word times, 0.9 s phrase gap)
   — but a pause is not a sentence end: read the words around each cut and judge by meaning; set `hard_a/hard_b` where needed.
   Breathing/panting events must not count as speech (SKIP_EV). `'sp'` pieces are auto-tightened (`tight=False` to keep pauses).
   Also cut: false starts + "เอาใหม่" retakes, off-topic tangents (flood/other provinces), self-deprecating asides the user
   may not want public (money complaints, "ดูสภาพผม") — when unsure, keep it but list it for the user to decide. Fill `project.json` (title, subtitle, stats_line, summary_lines from the FIT summary).
   `python build.py proxy --plan` (cwd `<project>/work`, run `scripts/build.py` by path) prints section start times + total.
8. **Music** — set `XI_KEY`; `build.py` generates one ElevenLabs instrumental per music cue sized to its section (≤2 concurrent),
   plus a whoosh SFX. Audition a style first with `scripts/music.py` if the user wants. Mix: music ducks under speech
   (sidechain), loudnorm −14 LUFS. Rock/metal works for action/descent; keep lighter music under dialogue/jokes.
   Talk must win: per-piece speech gain to `speech_lufs` (−19) + music volume dropped to ~0.13 under every talk range
   (deterministic duck, not only sidechain). Music shorter than its section is crossfade-looped, never slowed down.
   Cached tracks are never regenerated (costs credits) — delete one on purpose to remake it.
9. ✋ **Rough cut** — `XI_KEY=… work/venv/bin/python -I scripts/build.py proxy` (~1–2 min) → `output/<name>_proxy.mp4`.
   QA yourself first: a 1-frame-per-12-s tile of the output, `ebur128` loudness, `silencedetect` for holes. Then ask the user
   for timestamped notes ("2:27 ตัดเร็วไป", "5:14 ใส่แว่นให้ไก่ 4 วิ"). Map a timestamp to the source with the timeline in
   `--plan` / TL. Iterate; each rebuild only re-renders changed pieces.
10. **Graphics/memes on request** — stickers via `project.json.stickers` (PNG, t0/t1, bounce/slide, wobble); tracked
    sunglasses+chain via `bling` + `track` keyframes (find eye positions from a gridded frame tile every 2 s); fuel-gauge and
    SUB-X stamp gags via `fx`. Need a PNG the user links from a stock site that needs login? Generate one with `scripts/image.py`
    on flat green, then `scripts/sprite_key.py`. Overlays should be short (2–4 s) unless asked.
11. ✋ **Cover** — poster style matching the event's visual identity. Best result: AI repaint of a **real frame** via
    `scripts/image.py` with a public https ref URL (ask the user to upload, e.g. ibb.co, or get consent before you upload a
    personal photo). Describe the person precisely (gender, hair, cap, clothes, pose) or the model swaps them; ask for "person at
    medium-far distance, ~22 % of image height" and "upper 25 % empty for title". Put Thai text on with `scripts/cover.py`
    (models garble Thai). Offer 2–3 variants (photo / ink-etching / anime-sky) and iterate.
12. ✋ **Final** — `scripts/build.py final` (4K30 HEVC 45 Mbps; ~20 min on M1 Pro for a 9.5 min edit, ≈2.7 GB;
    a 30 min edit ≈ 8.5 GB and several hours). Run it under `caffeinate -i`. Pieces are cached (`seg_final/N.mp4` + `.key`),
    so a killed/failed render resumes — **don't restart from scratch**. If no new `seg_final` file appears for >15 min and
    ffmpeg CPU time stops growing, VideoToolbox is hung: kill it and rerun (run() now times out at 30 min and retries once).
    A hang that repeats on the same piece is that piece's filter graph (PST100: tpad freeze + `-af …apad` → hang; fixed by
    putting audio in the filter graph with `apad=whole_dur`). Reproduce the one ffmpeg command with a 90 s timeout to bisect.
    Then `scripts/srt.py <project>` → YouTube .srt, and `scripts/line_split.sh` → 720p parts ≤3 min (~25–50 MB) cut at section
    starts, each with a "n/N" badge — **ask first whether LINE parts are wanted** (PST100: not needed).
    QA frames from the final file. Offer to delete `work/seg_*`/`proxy` (~8 GB) only when asked.
13. **Publish kit** (offer after the final):
    - YouTube title options + description (story hook, Garmin stats, **Chapters with times from the final timeline**,
      credits, hashtags) + tags. No finish time/rank in title, cover or description (spoiler rule). Verify the location
      (province) from the race map, don't guess.
    - Facebook: upload natively (link posts get suppressed). Personal profiles **cannot set a custom thumbnail** — make
      `<name>_facebook_1080p.mp4` with the cover held 1.5 s at the start (h264_videotoolbox 10 Mbps, ~1.9 GB / 30 min) and a
      subtitle copy shifted +1.5 s (`ffmpeg -itsoffset 1.5 -i x.srt -c copy <name>_facebook_1080p.th_TH.srt`; FB needs the
      `.th_TH.srt` suffix).
    - Reels/Shorts teaser: `scripts/reel.py <project>` (settings in project.json `reel`) → 9:16, theme-coloured poster frame,
      16:9 window, CTA pill, whole-course profile, end card. Hook + montage (~45 s) works. FB Reels: link to the full FB post in
      the first comment and pin that post; YT Shorts: use "Related video". Keep the end-card text platform-neutral.

## Rules & lessons
- **No spoilers**: never show finish time, rank or result before the story reaches the finish — not in the hook, montage,
  title card, HUD stats, cover or description. Results go at the finish only.
- **Light inserts**: short text banners (2 lines) beat full-screen data cards/tables; users removed every dense card.
  Station card = profile + "อยู่ตรงนี้ ▼" + next station; no elapsed time, no per-km pace bars.
- No rank-chasing / "overtaking everyone" narrative unless the user asks; no "edited by" end card by default (`end_card`).
- Chapter = one race leg (START → A1, A1 → A2 …) plus named moments (the hardest climb, the night); keep the card ~5 s.
- HUD for races: current leg + next station + distance to it + clock time; a small down-arrow marker reads better than a dot.
- Photos (phone/photographer): place by EXIF/content; photographer file-name times are not capture times. Photos with no
  EXIF time → `hud=False`. A result slip with name/bib: ask once whether it may be shown.
- Every user timestamp refers to the proxy they watched — keep old EDLs (edl_v1, v2 …) to map times after re-cuts.
- Always reply in Thai, including progress updates.
- Never modify/delete originals. Ask before deleting anything. Keep every file inside the project folder.
- API keys only from env (`XI_KEY`, `GETPOD_KEY`); never write them into files. If the user pastes a key in chat, use it but
  remind them to rotate it afterwards.
- Logos/trademarks: the user decides. If they ask to put an event logo on, do it (small, theme-colored box) — just mention
  YouTube claim/sponsorship-impression risk once, don't lecture.
- Thai text: libass + Kanit renders shaping correctly; Thai has no spaces, so break lines at word/phrase boundaries yourself.
- Report honestly: render-time guesses were off 2× before — quote ranges and say when you're unsure (e.g. LINE limits).
- Hardware: on macOS `build.py` uses VideoToolbox; elsewhere it falls back to libx265/libx264 (much slower; warn the user).
- Theme colors: `project.json.theme` (`primary`, `paper`, `accent`, `light`) recolor every graphic; match the event poster.

## Cost notes
ElevenLabs: Scribe ≈ 40 min audio per run, ~7 music tracks of 25–130 s, 1 SFX. Image provider: ~5,000 credits per image;
a cover usually takes 2–4 tries; tell the user the running total.
