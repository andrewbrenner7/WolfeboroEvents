#!/usr/bin/env python3
# events-component v1.2 2026-10
"""Shared events component (identical file on wolfeborooaks.com and sandcastletime.net).

Renders the events page, the schema.org JSON-LD and one static .ics file per event
from events/*.json at build time (Python stdlib only). The only per-site inputs are
the data file and the region settings in scripts/events_config.json.

Page parts: Plan ahead (annual list), Coming up (month-grouped list with a month bar
and category filters), add-to-calendar (.ics + Google Calendar). Styles live in
assets/events/events-component.css and the optional script in
assets/events/events-component.js (same version on both sites).

Optional data fields (all have fallbacks): top level timezone, state, guide_url;
per event start_time, end_time (HH:MM), occurrences (list of YYYY-MM-DD or
{date, start_time, end_time}), rrule, exdates, organizer, related_links;
per annual item next_start, next_end, next_text, title_note.
Never renders note, watch_list, source_url text or comments.
Config: scripts/events_component_config.json. Rebuild after each monthly data update and weekly so past events drop off.
"""
import datetime as dt
import html
import json
import os
import pathlib
import re
import sys
import urllib.parse

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

VERSION = "events-component v1.2 2026-10"
E = html.escape
ROOT = pathlib.Path(__file__).resolve().parent.parent
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Display groups (R8). Unknown categories fall into "town".
GROUPS = [
    ("arts", "Music and arts", ("music", "arts", "theater", "film")),
    ("market", "Markets", ("market",)),
    ("family", "Family and holidays", ("family", "holiday")),
    ("outdoors", "Outdoors and winter", ("outdoors", "winter", "race")),
    ("town", "Town and seasons", ("community", "school", "seasonal")),
]
GROUP_LABEL = {k: label for k, label, _ in GROUPS}
REGION_DEFAULTS = {
    "wolfeboro": {"timezone": "America/New_York", "state": "NH", "guide_url": "/guide/"},
    "port-townsend": {"timezone": "America/Los_Angeles", "state": "WA", "guide_url": "/port-townsend/"},
}
VTZ = {
    "America/New_York": ("-0500", "-0400", "EST", "EDT"),
    "America/Los_Angeles": ("-0800", "-0700", "PST", "PDT"),
}
STATUSES = ("confirmed", "tentative", "canceled")
MDL = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


class DataError(Exception):
    pass


# ---------- small helpers ----------

def group_of(cat):
    for k, _, cats in GROUPS:
        if cat in cats:
            return k
    return "town"


def pdate(v, eid, field):
    try:
        return dt.date.fromisoformat(str(v))
    except Exception:
        raise DataError("event %s: %s %r is not a YYYY-MM-DD date" % (eid, field, v))


def ptime(v, eid, field):
    if v in (None, ""):
        return None
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", str(v))
    if not m:
        raise DataError("event %s: %s %r is not HH:MM (24-hour)" % (eid, field, v))
    return dt.time(int(m.group(1)), int(m.group(2)))


def mon_d(d):
    return "%s %d" % (ABBR[d.month - 1], d.day)


def fmt_range(a, b):
    if a == b:
        return "%s %d, %d" % (ABBR[a.month - 1], a.day, a.year)
    if a.year == b.year and a.month == b.month:
        return "%s %d to %d, %d" % (ABBR[a.month - 1], a.day, b.day, a.year)
    if a.year == b.year:
        return "%s %d to %s %d, %d" % (ABBR[a.month - 1], a.day, ABBR[b.month - 1], b.day, a.year)
    return "%s %d, %d to %s %d, %d" % (ABBR[a.month - 1], a.day, a.year, ABBR[b.month - 1], b.day, b.year)


def fmt_text_dates(s):
    s = re.sub(r"(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})",
               lambda m: fmt_range(dt.date.fromisoformat(m.group(1)), dt.date.fromisoformat(m.group(2))), s)
    return re.sub(r"\d{4}-\d{2}-\d{2}", lambda m: fmt_range(*(dt.date.fromisoformat(m.group(0)),) * 2), s)


def md(text):
    """Escape text and turn [label](url) into links."""
    out, i = [], 0
    for m in MDL.finditer(text):
        out.append(E(text[i:m.start()]))
        out.append('<a href="%s">%s</a>' % (E(m.group(2)), E(m.group(1))))
        i = m.end()
    out.append(E(text[i:]))
    return "".join(out)


def plain(text):
    return MDL.sub(r"\1", text or "")


def clean_title(t):
    return re.sub(r"\s*\(tentative\)\s*$", "", t, flags=re.I)


def short_title(t):
    return re.sub(r"\s*\([^)]*\)\s*$", "", clean_title(t))


def place_name(venue, town):
    """Venue name without street numbers (no street address in schema)."""
    if not venue:
        return town
    v = re.sub(r"\s*\([^)]*\d[^)]*\)", "", venue)
    parts = [p.strip() for p in v.split(",") if p.strip() and not re.match(r"\d", p.strip())]
    return ", ".join(parts) or town


def tzinfo(name):
    if ZoneInfo:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    std, dst, _, _ = VTZ.get(name, ("+0000", "+0000", "UTC", "UTC"))

    class _Fixed(dt.tzinfo):  # fallback: US DST rules
        def utcoffset(self, d):
            return self._off(d)

        def dst(self, d):
            return dt.timedelta(0)

        def _off(self, d):
            y = d.year
            start = dt.datetime(y, 3, 8 + (6 - dt.date(y, 3, 8).weekday()) % 7, 2)
            end = dt.datetime(y, 11, 1 + (6 - dt.date(y, 11, 1).weekday()) % 7, 2)
            s = dst if start <= d.replace(tzinfo=None) < end else std
            return dt.timedelta(hours=int(s[:3]), minutes=int(s[0] + s[3:]))
    return _Fixed()


def iso_local(d, t, tz):
    """ISO date-time with the correct offset for that date."""
    x = dt.datetime.combine(d, t).replace(tzinfo=tz)
    off = x.utcoffset()
    mins = int(off.total_seconds() // 60)
    sign = "-" if mins < 0 else "+"
    mins = abs(mins)
    return "%sT%s:00%s%02d:%02d" % (d.isoformat(), t.strftime("%H:%M"), sign, mins // 60, mins % 60)


# ---------- validation and normalising ----------

def load(cfg):
    data_path = ROOT / cfg["data"]
    legacy_path = ROOT / "events" / "events-wolfeboro-v2.json"
    if data_path.exists() and legacy_path.exists():
        # Keep data/events.json and events/events-wolfeboro-v2.json in sync (whichever is newer)
        if legacy_path.stat().st_mtime > data_path.stat().st_mtime + 1:
            data_path.write_bytes(legacy_path.read_bytes())
        elif data_path.read_bytes() != legacy_path.read_bytes():
            legacy_path.write_bytes(data_path.read_bytes())
    data = json.loads(data_path.read_text(encoding="utf-8"))
    region = data.get("region", "")
    rd = REGION_DEFAULTS.get(region, {})
    site = {
        "timezone": data.get("timezone") or cfg.get("timezone") or rd.get("timezone", "America/New_York"),
        "state": data.get("state") or cfg.get("state") or rd.get("state", ""),
        "guide_url": data.get("guide_url") or cfg.get("guide_url") or rd.get("guide_url", "/"),
    }
    if "last_checked" not in data:
        raise DataError("top level: last_checked is missing")
    pdate(data["last_checked"], "(top level)", "last_checked")
    seen = set()
    for ev in data.get("events", []):
        eid = ev.get("id") or "(no id: %s)" % ev.get("title", "?")
        for f in ("id", "title", "start", "end", "town", "category", "summary", "url"):
            if not ev.get(f):
                raise DataError("event %s: required field %s is missing" % (eid, f))
        if eid in seen:
            raise DataError("event %s: id is used twice" % eid)
        seen.add(eid)
        s, e = pdate(ev["start"], eid, "start"), pdate(ev["end"], eid, "end")
        if e < s:
            raise DataError("event %s: end %s is before start %s" % (eid, e, s))
        if ev.get("status", "confirmed") not in STATUSES:
            raise DataError("event %s: status %r must be confirmed, tentative or canceled" % (eid, ev.get("status")))
        ptime(ev.get("start_time"), eid, "start_time")
        ptime(ev.get("end_time"), eid, "end_time")
        if ev.get("verified_on"):
            pdate(ev["verified_on"], eid, "verified_on")
        for o in ev.get("occurrences") or []:
            od = o if not isinstance(o, dict) else o.get("date")
            pdate(od, eid, "occurrences")
            if isinstance(o, dict):
                ptime(o.get("start_time"), eid, "occurrences start_time")
                ptime(o.get("end_time"), eid, "occurrences end_time")
        for x in ev.get("exdates") or []:
            pdate(x, eid, "exdates")
    for a in data.get("annual", []):
        aid = a.get("title", "(untitled annual item)")
        if not a.get("title") or not a.get("source_url"):
            raise DataError("annual %s: title and source_url are required" % aid)
        for f in ("next_start", "next_end"):
            if a.get(f):
                pdate(a[f], aid, f)
    return data, site


def occurrences(ev):
    out = []
    for o in ev.get("occurrences") or []:
        if isinstance(o, dict):
            out.append((dt.date.fromisoformat(str(o["date"])), ptime(o.get("start_time"), ev["id"], "x") or ptime(ev.get("start_time"), ev["id"], "x"),
                        ptime(o.get("end_time"), ev["id"], "x") or ptime(ev.get("end_time"), ev["id"], "x")))
        else:
            out.append((dt.date.fromisoformat(str(o)), ptime(ev.get("start_time"), ev["id"], "x"), ptime(ev.get("end_time"), ev["id"], "x")))
    return sorted(out)


# ---------- calendar output ----------

def ics_escape(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def fold(line):
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    out, cur, limit = [], b"", 75
    for ch in line:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > limit:
            out.append(cur.decode("utf-8"))
            cur, limit = b" ", 75
        cur += cb
    out.append(cur.decode("utf-8"))
    return "\r\n".join(out)


def vtimezone(name):
    std, dst, sn, dn = VTZ[name]
    return ["BEGIN:VTIMEZONE", "TZID:" + name,
            "BEGIN:DAYLIGHT", "TZOFFSETFROM:" + std, "TZOFFSETTO:" + dst, "TZNAME:" + dn,
            "DTSTART:19700308T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT",
            "BEGIN:STANDARD", "TZOFFSETFROM:" + dst, "TZOFFSETTO:" + std, "TZNAME:" + sn,
            "DTSTART:19701101T020000", "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD",
            "END:VTIMEZONE"]


def location_text(ev, site):
    return ", ".join(x for x in [ev.get("venue"), ev.get("town"), site["state"]] if x)


def cal_entries(ev, today):
    """List of (start_date, end_date_inclusive, start_time, end_time, uid_suffix)."""
    occ = occurrences(ev)
    if occ:
        return [(d, d, st, et, d.strftime("%Y%m%d")) for d, st, et in occ if d >= today]
    s, e = dt.date.fromisoformat(str(ev["start"])), dt.date.fromisoformat(str(ev["end"]))
    st, et = ptime(ev.get("start_time"), ev["id"], "x"), ptime(ev.get("end_time"), ev["id"], "x")
    if ev.get("rrule"):
        return [(s, s, st, et, "")]
    return [(s, e, st, et, "")]


def cal_eligible(ev):
    if ev.get("status") == "canceled":
        return False
    if ev.get("occurrences") or ev.get("rrule"):
        return True
    s, e = dt.date.fromisoformat(str(ev["start"])), dt.date.fromisoformat(str(ev["end"]))
    return (e - s).days < 7  # spans of more than 7 days get "See the schedule" instead


def build_ics(ev, cfg, site, today, stamp):
    tzn = site["timezone"]
    tz = tzinfo(tzn)
    status = ev.get("status", "confirmed")
    title = clean_title(ev["title"])
    summary = ("Tentative: " if status == "tentative" else "") + title
    checked = ev.get("verified_on") or ""
    desc = "%s\nDetails: %s\nDate checked %s. Check the organizer's page before you go." % (plain(ev["summary"]), ev["url"], checked)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//%s//events//EN" % cfg["domain"],
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    entries = cal_entries(ev, today)
    timed = any(x[2] for x in entries)
    if timed:
        lines += vtimezone(tzn)
    for s, e, st, et, suf in entries:
        uid = "%s%s@%s" % (ev["id"], "-" + suf if suf else "", cfg["domain"])
        lines += ["BEGIN:VEVENT", "UID:" + uid, "DTSTAMP:" + stamp]
        if st:
            lines.append("DTSTART;TZID=%s:%s" % (tzn, dt.datetime.combine(s, st).strftime("%Y%m%dT%H%M%S")))
            if et:
                lines.append("DTEND;TZID=%s:%s" % (tzn, dt.datetime.combine(e if e != s and not ev.get("rrule") else s, et).strftime("%Y%m%dT%H%M%S")))
        else:
            lines.append("DTSTART;VALUE=DATE:" + s.strftime("%Y%m%d"))
            lines.append("DTEND;VALUE=DATE:" + (e + dt.timedelta(days=1)).strftime("%Y%m%d"))
        if ev.get("rrule"):
            rule = str(ev["rrule"]).replace("RRULE:", "")
            if "UNTIL=" not in rule and "COUNT=" not in rule:
                end = dt.date.fromisoformat(str(ev["end"]))
                if st:
                    u = dt.datetime.combine(end, dt.time(23, 59, 59)).replace(tzinfo=tz).astimezone(dt.timezone.utc)
                    rule += ";UNTIL=" + u.strftime("%Y%m%dT%H%M%SZ")
                else:
                    rule += ";UNTIL=" + end.strftime("%Y%m%d")
            lines.append("RRULE:" + rule)
            for x in ev.get("exdates") or []:
                xd = dt.date.fromisoformat(str(x))
                if st:
                    lines.append("EXDATE;TZID=%s:%s" % (tzn, dt.datetime.combine(xd, st).strftime("%Y%m%dT%H%M%S")))
                else:
                    lines.append("EXDATE;VALUE=DATE:" + xd.strftime("%Y%m%d"))
        lines += ["SUMMARY:" + ics_escape(summary),
                  "LOCATION:" + ics_escape(location_text(ev, site)),
                  "DESCRIPTION:" + ics_escape(desc),
                  "URL:" + ev["url"],
                  "STATUS:" + {"confirmed": "CONFIRMED", "tentative": "TENTATIVE", "canceled": "CANCELLED"}[status],
                  "TRANSP:TRANSPARENT" if not st else "TRANSP:OPAQUE",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(x) for x in lines) + "\r\n"


def google_link(ev, site, today):
    entries = cal_entries(ev, today)
    if not entries:
        return None
    s, e, st, et, _ = entries[0]
    if st:
        a = dt.datetime.combine(s, st).strftime("%Y%m%dT%H%M%S")
        b = dt.datetime.combine(e if not ev.get("rrule") else s, et).strftime("%Y%m%dT%H%M%S") if et else a
    else:
        a, b = s.strftime("%Y%m%d"), (e + dt.timedelta(days=1)).strftime("%Y%m%d")
    status = ev.get("status", "confirmed")
    q = [("action", "TEMPLATE"),
         ("text", ("Tentative: " if status == "tentative" else "") + clean_title(ev["title"])),
         ("dates", a + "/" + b), ("ctz", site["timezone"]),
         ("details", "%s\nDetails: %s" % (plain(ev["summary"]), ev["url"])),
         ("location", location_text(ev, site))]
    if ev.get("rrule"):
        rule = str(ev["rrule"]).replace("RRULE:", "")
        if "UNTIL=" not in rule and "COUNT=" not in rule:
            rule += ";UNTIL=" + dt.date.fromisoformat(str(ev["end"])).strftime("%Y%m%d")
        q.append(("recur", "RRULE:" + rule))
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)


def cal_links_html(ics_href, gurl, title):
    return ('<div class="ev-cal"><a href="%s" download>Apple or Outlook (.ics)<span class="ev-sr"> file for %s</span></a>'
            '<a href="%s" target="_blank" rel="noopener">Google Calendar<span class="ev-sr"> for %s (opens in a new tab)</span></a></div>'
            % (E(ics_href), E(title), E(gurl), E(title)))


# ---------- page ----------

def month_key(d):
    return (d.year, d.month)


def next_month(ym):
    y, m = ym
    return (y + 1, 1) if m == 12 else (y, m + 1)


def build(cfg, today, stamp):
    data, site = load(cfg)
    tz = tzinfo(site["timezone"])
    base = cfg["base_path"]
    cal_dir = (ROOT / cfg["out"]).parent / "cal"
    cal_dir.mkdir(parents=True, exist_ok=True)
    for old in cal_dir.glob("*.ics"):
        old.unlink()
    town_label = cfg["town_label"]
    guide = site["guide_url"]
    checked = dt.date.fromisoformat(str(data["last_checked"]))

    # ----- Plan ahead -----
    def first_date(a):
        if a.get("next_start"):
            return str(a["next_start"])
        m = re.search(r"\d{4}-\d{2}-\d{2}", str(a.get("next_confirmed", "")))
        return m.group(0) if m else "9999"

    annual = sorted(data.get("annual", []), key=lambda a: (a.get("tier", 9), first_date(a), a["title"]))
    cards = []
    for i, a in enumerate(annual):
        nxt = str(a.get("next_confirmed", "")).strip()
        past = a.get("next_end") and dt.date.fromisoformat(str(a["next_end"])) < today
        if past or not nxt or "not posted" in nxt.lower():
            next_html = '<p class="ev-next ev-tba">%s</p>' % E(cfg.get("not_posted_text", "Next year's date isn't out yet"))
        else:
            next_html = '<p class="ev-next">%s</p>' % E(a.get("next_text") or ("Next: " + fmt_text_dates(nxt)))
        add = ""
        if a.get("next_start") and not past and dt.date.fromisoformat(str(a["next_start"])) >= today:
            aid = "annual-" + re.sub(r"[^a-z0-9]+", "-", a["title"].lower()).strip("-")
            pseudo = {"id": aid, "title": a["title"], "start": a["next_start"], "end": a.get("next_end") or a["next_start"],
                      "summary": a.get("typical", ""), "url": a["source_url"], "town": a.get("town", ""),
                      "status": "confirmed", "verified_on": data["last_checked"]}
            (cal_dir / (aid + ".ics")).write_bytes(build_ics(pseudo, cfg, site, today, stamp).encode("utf-8"))
            add = ('<details class="ev-add"><summary>Add to calendar</summary>%s</details>'
                   % cal_links_html(base + "cal/" + aid + ".ics", google_link(pseudo, site, today), a["title"]))
        note = (" " + E(a["title_note"])) if a.get("title_note") else ""
        cls = ' class="ev-more"' if i >= 6 else ""
        cards.append('<li%s><h3><a href="%s">%s</a>%s</h3><p class="ev-typ">%s</p>%s%s</li>' % (
            cls, E(a["source_url"]), E(a["title"]), note, E(a.get("typical", "")), next_html, add))
    extra = len(annual) - 6
    more = ('<details class="ev-showmore"><summary>Show %d more annual event%s</summary></details>' % (extra, "" if extra == 1 else "s")
            if extra > 0 else "")
    plan_html = ('<section class="ev-sec ev-pa" id="plan-ahead" aria-labelledby="plan-ahead-h"><div class="ev-wrap">'
                 '<h2 class="section-title" id="plan-ahead-h">Plan ahead</h2>'
                 '<p class="ev-sub">The big annual events. Where organizers have posted next year&#x27;s dates, they&#x27;re here.</p>'
                 '<ul class="ev-annual">%s</ul>%s</div></section>' % ("".join(cards), more))

    # ----- Coming up: decide what is visible and where it goes -----
    rows = {}      # (y, m) -> list of (sort_key, html, ev)
    still = {}     # (y, m) -> list of html
    ld = []
    last_month = month_key(today)
    groups_used = set()
    visible = 0
    for ev in data.get("events", []):
        s, e = dt.date.fromisoformat(str(ev["start"])), dt.date.fromisoformat(str(ev["end"]))
        status = ev.get("status", "confirmed")
        occ = [o for o in occurrences(ev) if o[0] >= today]
        if ev.get("occurrences"):
            if not occ:
                continue
            placements = []
            for ym in sorted({month_key(o[0]) for o in occ}):
                mo = [o for o in occ if month_key(o[0]) == ym]
                placements.append((ym, mo[0][0], mo[-1][0], mo))
            last = occ[-1][0]
        else:
            if e < today:
                continue
            ym = month_key(max(s, today))
            placements = [(ym, s, e, None)]
            last = e
        if status == "canceled" and placements[0][0] < month_key(today):
            continue
        visible += 1
        g = group_of(ev["category"])
        groups_used.add(g)
        title = clean_title(ev["title"])
        eligible = cal_eligible(ev)
        ics_href = base + "cal/" + ev["id"] + ".ics"
        if eligible:
            (cal_dir / (ev["id"] + ".ics")).write_bytes(build_ics(ev, cfg, site, today, stamp).encode("utf-8"))
            gurl = google_link(ev, site, today)
        last_month = max(last_month, month_key(last), *(p[0] for p in placements))
        tier = ev.get("tier", 3)
        for ym, show_s, show_e, mo in placements:
            # time line
            st = ptime(ev.get("start_time"), ev["id"], "x")
            if mo:
                st = mo[0][1]
            ttext = ev.get("time") or ev.get("recurrence") or ""
            if mo and len(occ) > 1 and not ev.get("time"):
                ttext = (ev.get("recurrence") or "")
            place = ", ".join(x for x in [ev.get("venue"), ev.get("town")] if x)
            if ttext and st:
                tl = '<time datetime="%sT%s">%s</time>' % (show_s.isoformat(), st.strftime("%H:%M"), E(ttext))
            else:
                tl = E(ttext)
            meta = (tl + " · " if tl else "") + E(place)
            if mo and len(mo) > 1:
                meta = E("Dates this month: " + ", ".join(mon_d(o[0]) for o in mo)) + "<br>" + meta
            # date block
            to = ""
            if show_e != show_s and not mo:
                to = '<span class="ev-to">to <time datetime="%s">%s</time></span>' % (show_e.isoformat(), mon_d(show_e))
            elif mo and len(mo) > 1:
                to = '<span class="ev-to">+%d more</span>' % (len(mo) - 1)
            if show_s < today and not mo:
                # Already running: show the end date, not a start date in the past.
                dblock = ('<div class="ev-date ev-running"><span class="ev-mo">Thru</span><time datetime="%s">'
                          '<span class="ev-d">%d</span><span class="ev-wd">%s</span></time></div>'
                          % (show_e.isoformat(), show_e.day, ABBR[show_e.month - 1]))
            else:
                dblock = ('<div class="ev-date"><time datetime="%s"><span class="ev-mo">%s</span>'
                          '<span class="ev-d">%d</span><span class="ev-wd">%s</span></time>%s</div>'
                          % (show_s.isoformat(), ABBR[show_s.month - 1], show_s.day, WD[show_s.weekday()], to))
            tags = ['<span class="ev-cat">%s</span>' % GROUP_LABEL[g]]
            if show_s < today and not mo:
                tags.append('<span class="ev-status">Running now</span>')
            if status == "tentative":
                tags.append('<span class="ev-status">Tentative</span>')
            if status == "canceled":
                tags.append('<span class="ev-status ev-cxl">Canceled</span>')
            if tier in (1, 2):
                tags.append('<span class="ev-annualtag">Annual</span>')
            # disclosure
            inner = []
            if status == "canceled":
                pass
            elif eligible:
                inner.append(cal_links_html(ics_href, gurl, title))
            else:
                inner.append('<div class="ev-cal"><a href="%s">See the schedule<span class="ev-sr"> for %s</span></a></div>' % (E(ev["url"]), E(title)))
            fine = []
            if ev.get("venue_url"):
                fine.append('Venue: <a href="%s">%s</a>.' % (E(ev["venue_url"]), E(place_name(ev.get("venue"), ev.get("town")))))
            for name, u in (ev.get("related_links") or {}).items():
                fine.append('<a href="%s">%s</a>.' % (E(u), E(name)))
            if ev.get("verified_on"):
                vd = dt.date.fromisoformat(str(ev["verified_on"]))
                fine.append("Date checked %s with the organizer. Plans change, so check their page before you go." % mon_d(vd))
            if fine:
                inner.append('<p class="ev-fine">%s</p>' % " ".join(fine))
            summ = "Add to calendar" if status != "canceled" else "Details"
            if status != "canceled" and not eligible:
                summ = "Schedule and details"
            disc = '<details class="ev-add"><summary>%s<span class="ev-sr">: %s</span></summary>%s</details>' % (summ, E(title), "".join(inner))
            cls = "ev k-%s%s" % (g, " ev-canceled" if status == "canceled" else "")
            row = ('<li class="%s" data-cat="%s" data-end="%s">%s<div class="ev-body"><h4><a href="%s">%s</a></h4>'
                   '<p class="ev-meta">%s</p><p class="ev-sum">%s</p><div class="ev-tags">%s</div>%s</div></li>'
                   % (cls, g, (mo[-1][0] if mo else show_e).isoformat(), dblock, E(ev["url"]), E(title), meta,
                      md(ev["summary"]), "".join(tags), disc))
            rows.setdefault(ym, []).append(((show_s, tier, title), row))
        # still running (no occurrences, spans later months)
        if not ev.get("occurrences") and status != "canceled":
            ym = next_month(placements[0][0])
            while ym <= month_key(e):
                rec = ev.get("recurrence") or ""
                rec = re.split(r"\s*[;(]|:\s", rec)[0].strip().rstrip(",") if rec else ""
                bits = '<a href="%s">%s</a>%s (through %s)' % (E(ev["url"]), E(short_title(ev["title"])), (", " + E(rec)) if rec else "", mon_d(e))
                still.setdefault(ym, []).append((s, bits, g))
                ym = next_month(ym)
        # JSON-LD
        entries = [(o[0], o[0], o[1], o[2]) for o in occ][:12] if ev.get("occurrences") else [(s, e, ptime(ev.get("start_time"), ev["id"], "x"), ptime(ev.get("end_time"), ev["id"], "x"))]
        for a, b, st, et in entries:
            item = {"@context": "https://schema.org", "@type": "Event", "name": title,
                    "description": plain(ev["summary"]),
                    "startDate": iso_local(a, st, tz) if st else a.isoformat(),
                    "endDate": iso_local(b, et, tz) if (st and et) else b.isoformat(),
                    "eventStatus": "https://schema.org/EventCancelled" if status == "canceled" else "https://schema.org/EventScheduled",
                    "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
                    "location": {"@type": "Place", "name": place_name(ev.get("venue"), ev["town"]),
                                 "address": {"@type": "PostalAddress", "addressLocality": ev["town"],
                                             "addressRegion": site["state"], "addressCountry": "US"}},
                    "url": ev["url"]}
            if ev.get("organizer"):
                item["organizer"] = {"@type": "Organization", "name": ev["organizer"]}
            ld.append(item)

    # ----- month bar + sections -----
    months = []
    ym = month_key(today)
    while ym <= last_month:
        months.append(ym)
        ym = next_month(ym)
    chips, secs = [], []
    prev_year = None
    for (y, m) in months:
        mid = "m-%04d-%02d" % (y, m)
        month_rows = rows.get((y, m), [])
        # Soonest first. Events already running (started before the build date) go
        # below every upcoming dated item in the month, so a dated event such as a
        # ski opening always leads. Past events never get here: anything whose end
        # date (or last occurrence) is before the build date is dropped above.
        def sort_key(k):
            show_s, tier, title = k
            return (1 if show_s < today else 0, show_s, tier, title)
        items = [r for _, r in sorted(month_rows, key=lambda x: sort_key(x[0]))]
        n = len(items)
        label = ABBR[m - 1] + (" %d" % y if prev_year is not None and y != prev_year else "")
        prev_year = y
        chips.append('<li><a class="ev-chip ev-mchip%s" href="#%s" data-m="%s">%s<span class="ev-n">%d</span>'
                     '<span class="ev-sr"> events</span></a></li>' % (" ev-zero" if n == 0 else "", mid, mid, label, n))
        sec = ['<section class="ev-month" id="%s" aria-labelledby="%s-h"><h3 class="ev-month-h" id="%s-h">%s %d</h3>' % (mid, mid, mid, MONTHS[m - 1], y)]
        st_items = sorted(still.get((y, m), []))
        if st_items:
            sec.append('<p class="ev-still"><strong>Still running:</strong> %s</p>'
                       % " · ".join('<span data-cat="%s">%s</span>' % (g, b) for _, b, g in st_items))
        empty_msg = ('<p class="ev-empty">Nothing on our list for %s yet. We add events on the first Monday of each month. '
                     'In the meantime, see <a href="#plan-ahead">Plan ahead</a> or the <a href="%s">%s guide</a>.</p>'
                     % (MONTHS[m - 1], E(guide), E(town_label)))
        if items:
            sec.append('<ul class="ev-list">%s</ul>' % "".join(items))
        else:
            sec.append(empty_msg)
        sec.append('<p class="ev-nomatch" hidden></p></section>')
        secs.append("".join(sec))

    filt = ['<button type="button" class="ev-chip ev-fchip" aria-pressed="true" data-f="all">All</button>']
    for k, label, _ in GROUPS:
        if k in groups_used:
            filt.append('<button type="button" class="ev-chip ev-fchip k-%s" aria-pressed="false" data-f="%s">'
                        '<span class="ev-dot" aria-hidden="true"></span>%s</button>' % (k, k, label))
    if visible:
        body = ('<nav class="ev-bar" aria-label="Jump to month"><ul class="ev-row">%s</ul></nav>'
                '<div class="ev-filters ev-row" role="group" aria-label="Show events by type" hidden>%s</div>'
                '<p class="ev-sr" aria-live="polite" id="ev-count"></p>%s'
                % ("".join(chips), "".join(filt), "".join(secs)))
    else:
        body = "<p class=\"ev-empty\">We&#x27;re between seasons. New events go up on the first Monday of each month.</p>"
    coming_html = ('<section class="ev-sec ev-cu" id="coming-up" aria-labelledby="coming-up-h"><div class="ev-wrap">'
                   '<h2 class="section-title" id="coming-up-h">Coming up</h2>%s</div></section>' % body)

    component = "<!-- %s -->\n%s\n%s\n" % (VERSION, plan_html, coming_html)
    tpl = (ROOT / cfg["template"]).read_text(encoding="utf-8")
    updated = "Updated %s %d. Dates checked with organizers on %s." % (MONTHS[checked.month - 1], checked.year, mon_d(checked))
    jsonld = json.dumps(ld, ensure_ascii=False, indent=1).replace("</", "<\\/")
    out = (tpl.replace("{{UPDATED}}", E(updated))
              .replace("{{EVENTS_COMPONENT}}", component)
              .replace("{{JSONLD}}", jsonld))
    if "{{" in out:
        raise DataError("template %s still has an unfilled {{placeholder}}" % cfg["template"])
    if "\u2014" in out:
        raise DataError("an em dash slipped into the page; please reword the data")
    dest = ROOT / cfg["out"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(out, encoding="utf-8")
    n_ics = len(list(cal_dir.glob("*.ics")))
    print("events: wrote %s (%d visible events, %d months, %d JSON-LD events, %d .ics files)"
          % (cfg["out"], visible, len(months), len(ld), n_ics))


def main():
    config = json.loads((ROOT / "scripts" / "events_component_config.json").read_text(encoding="utf-8"))
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    for cfg in config:
        tzname = cfg.get("timezone", "America/New_York")
        today = now.astimezone(tzinfo(tzname)).date()
        if os.environ.get("EVENTS_TODAY"):
            today = dt.date.fromisoformat(os.environ["EVENTS_TODAY"])
        try:
            build(cfg, today, stamp)
        except DataError as err:
            sys.exit("events build FAILED (%s): %s" % (cfg["data"], err))


if __name__ == "__main__":
    main()
