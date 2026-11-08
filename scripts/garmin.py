"""Garmin .FIT -> garmin/records.json + printed summary, km splits and stops (for clock alignment).
usage: python garmin.py <project_root> <file.fit> [utc_offset_hours=7]
records.json rows: [local_seconds_of_day, hr, altitude_m, distance_m, lat, lon]"""
import sys, os, json, datetime as dt, fitparse
root, fit = sys.argv[1], sys.argv[2]; tz = float(sys.argv[3]) if len(sys.argv) > 3 else 7
f = fitparse.FitFile(fit)
rows = []
for m in f.get_messages('record'):
    r = {d.name: d.value for d in m}; t = r['timestamp'] + dt.timedelta(hours=tz)
    la, lo = r.get('position_lat'), r.get('position_long')
    rows.append([t.hour * 3600 + t.minute * 60 + t.second, r.get('heart_rate'), r.get('enhanced_altitude') or r.get('altitude'),
                 r.get('distance'), la * 180 / 2**31 if la else None, lo * 180 / 2**31 if lo else None])
os.makedirs(os.path.join(root, 'garmin'), exist_ok=True)
json.dump(rows, open(os.path.join(root, 'garmin', 'records.json'), 'w'))
S = {d.name: d.value for m in f.get_messages('session') for d in m}
hms = lambda s: f'{int(s//3600):02d}:{int(s%3600//60):02d}:{int(s%60):02d}'
print(f"start {hms(rows[0][0])}  end {hms(rows[-1][0])}  records {len(rows)}")
for k in ('total_distance', 'total_elapsed_time', 'total_ascent', 'total_descent', 'avg_heart_rate', 'max_heart_rate', 'total_calories'):
    print(f'{k}: {S.get(k)}')
alts = [r[2] for r in rows if r[2]]; print(f'alt min {min(alts):.0f} max {max(alts):.0f}')
print('\nkm splits:')
for m in f.get_messages('lap'):
    d = {x.name: x.value for x in m}
    print(f"  {(d['start_time'] + dt.timedelta(hours=tz)).strftime('%H:%M')}  {d['total_distance']:.0f} m  {d['total_timer_time']/60:.0f} min  +{d.get('total_ascent')} m  hr {d.get('avg_heart_rate')}")
print('\nstops > 2.5 min (match these against the video to find the camera clock offset):')
run = None
for i, r in enumerate(rows):
    moving = i and (r[3] or 0) - (rows[i-1][3] or 0) > 0.2
    if not moving: run = run or r
    else:
        if run and r[0] - run[0] > 150: print(f'  {hms(run[0])} - {hms(r[0])}  km {(run[3] or 0)/1000:.2f}  alt {run[2]}')
        run = None
