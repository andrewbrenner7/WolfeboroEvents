"""Check: events in each month of index.html are sorted by badge date.
Run after the build: EVENTS_TODAY=2026-10-25 python3 scripts/events_component.py && python3 scripts/test_events_sort.py"""
import re, sys, pathlib
h = pathlib.Path(__file__).resolve().parent.parent.joinpath("index.html").read_text()
bad = 0
for m in re.finditer(r'<section class="ev-month" id="(m-[\d-]+)"(.*?)</section>', h, re.S):
    ds = [re.search(r'datetime="([\d-]+)', li).group(1) for li in re.findall(r'<li class="ev k.*?</li>', m.group(2), re.S)]
    if ds != sorted(ds):
        bad += 1
        print("out of order in", m.group(1), ds)
sys.exit(1 if bad else print("ok: events sorted by badge date"))
