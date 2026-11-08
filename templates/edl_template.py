# Edit decision list — the whole edit lives here. build.py reads it.
#
# sec(name, music_cue, chapter=None)      start a section; music_cue = key in build.py PROMPTS (or project.json music_prompts),
#                                          None = no music. chapter='ชื่อช่วง' shows a CHAPTER card + mini route map.
# g(clip, in_s, out_s, mode='sp', speed=1.0, **extras)
#   clip   clip number from the file name (DJI_..._0014_D.MP4 -> '0014')
#   mode   'sp'  speech: auto-tightened (silences/dead air removed using word timestamps), full original audio
#          'act' action: kept whole, original audio 70%
#          'br'  b-roll: original audio 25%; with speed>1 audio is muted (timelapse / speed ramp)
#   speed  >1 timelapse (2.5-3.0 typical for long running/walking), 0.5 slow-mo (60fps source)
#   extras (all optional):
#     cap='ข้อความ', cap_at=<clip s>        burned punchline caption (bottom, pops in)
#     call='ข้อความ'                         top-left callout tag (checkpoint, altitude, fun facts)
#     title=True                              title card over this shot (project.json title/subtitle/stats + GPS route)
#     card=True                               end summary card (project.json summary_lines + elevation profile)
#     fx='gauge', cap=..., cap_at=..., gauge_text='FULL!'          fuel-gauge gag next to the caption
#     fx='stamp', fx_at=<clip s>, stamp='SUB 10!', stamp_sub='...'  white flash + big slanted stamp + whoosh
#     bling=<clip s>, bling_dur=4.0, bling_label='...', track=[(clip_s, eye_x, eye_y), ...]
#                                              sunglasses + gold chain PNGs (sprites/glasses.png, chain.png) that
#                                              follow a head; eye coords in 1920x1080, keyframe every ~2 s
S = []
def sec(name, music, chapter=None): S.append({'name': name, 'music': music, 'chapter': chapter, 'segs': []})
def g(clip, a, b, mode='sp', speed=1.0, **kw): S[-1]['segs'].append(dict(clip=clip, a=a, b=b, mode=mode, speed=speed, **kw))

# Typical structure (target 8–10 min from ~40–90 min raw, keep ~15–20%):
sec('hook', None)                      # 5–10 s: the funniest/strongest line, no music
# g('0041', 67.9, 77.3, cap='...')
sec('montage', 'metal_hook')           # 15–25 s: fast b-roll at 2.5–3x, ends on the title card
# g('0031', 172, 178, 'br', 3.0)
# g('0021', 60, 66, 'br', 1.0, title=True)
sec('intro', 'pop')                    # gang intro, start line
sec('part1', 'rock', chapter='...')    # chapters follow the day: climb / views / food / descent ...
sec('finish', 'rock_end', chapter='...')
# g('0040', 8, 16, 'br', 1.0, card=True)   # summary card
