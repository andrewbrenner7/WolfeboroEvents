"""Check: Plan ahead cards are in next-occurrence order, and the date helper
handles typical phrases. Run after the build:
  EVENTS_TODAY=2026-10-25 python3 scripts/events_component.py && python3 scripts/test_plan_ahead_order.py [file]"""
import datetime as dt, pathlib, re, sys
here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(here))
import events_component as c
d = dt.date
assert c.typical_range("late May", 2027) == (d(2027, 5, 25), d(2027, 5, 25))
assert c.typical_range("early February, 3 days", 2027) == (d(2027, 2, 5), d(2027, 2, 7))
assert c.typical_range("July to early September", 2027) == (d(2027, 7, 1), d(2027, 9, 5))
assert c.typical_range("Columbus Day weekend, 3 days", 2026) == (d(2026, 10, 10), d(2026, 10, 12))
assert c.typical_range("the second weekend of August", 2027) == (d(2027, 8, 13), d(2027, 8, 15))
# rolls to next year once passed; multi-day range is still current until its end
assert c.annual_next({"typical": "late May"}, d(2026, 10, 25))[0] == d(2027, 5, 25)
assert c.annual_next({"typical": "July to early September"}, d(2026, 8, 1))[0] == d(2026, 7, 1)
f = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else here.parent / "index.html"
h = f.read_text()
sec = re.search(r'id="plan-ahead".*?</section>', h, re.S).group(0)
ds = re.findall(r'<li[^>]*data-next="([\d-]+)"', sec)
assert ds and ds == sorted(ds), "Plan ahead out of order: %s" % ds
print("ok: %d Plan ahead cards in next-occurrence order" % len(ds))
