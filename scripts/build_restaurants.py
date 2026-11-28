#!/usr/bin/env python3
"""Build /restaurants/index.html from data/restaurants.json and scripts/restaurants_template.html.

data/restaurants.json is the source of truth: weekly hours updates are JSON-only edits
(update hours, hours_checked, hours_confidence and the top-level last_checked).
Run before site_nav.py and apply_turnstile_pages.py (see netlify.toml)."""
import html, json, pathlib, re, datetime as dt

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = json.loads((ROOT / "data" / "restaurants.json").read_text(encoding="utf-8"))
E = html.escape
DAYS = ["mon","tue","wed","thu","fri","sat","sun"]
DAYN = dict(zip(DAYS, ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]))
MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
COLORS = {"pizza":"#9A2E1C","american-pub":"#5E4A12","seafood":"#1A567E","breakfast":"#B45309","cafe":"#6B4423",
          "bakery":"#8A5A83","sweets":"#C2410C","asian":"#25602A","mexican-latin":"#B91C1C","deli":"#3F6A58","fine-dining":"#5B2A86"}
CAT = {c["id"]: c["label"] for c in D["categories"]}
def tfmt(t):
    h, m = map(int, t.split(":")); s = "p.m." if h >= 12 else "a.m."; h = h % 12 or 12
    return "%d%s %s" % (h, "" if m == 0 else ":%02d" % m, s)
def dshort(iso):
    y, m, d = map(int, iso.split("-")); return "%s %d" % (MON[m-1], d)
def rows(r):
    out = []
    for d in DAYS:
        v = r["hours"][d]
        if v is None: txt = "Not confirmed, call ahead"
        elif not v: txt = "Closed"
        else: txt = ", ".join("%s to %s" % (tfmt(a), tfmt(b)) for a, b in v)
        out.append('<tr data-d="%s"><th scope="row">%s</th><td>%s</td></tr>' % (d, DAYN[d][:3], E(txt)))
    return "".join(out)
BANNED = ("huckshoagies.com", "thesandtrap.com")
def site(r):
    """Website to link, or None. A site flagged unverified in the JSON is not linked until the flag is cleared."""
    w = r.get("website")
    if not w or (r.get("website_check") or {}).get("status") == "unverified": return None
    assert not any(b in w for b in BANNED), "banned domain for %s" % r["id"]
    return w
rs = D["restaurants"]
order = {"open": 0, "temporarily_closed": 1, "preorder_only": 2, "closed_for_season": 3}
rs = sorted(rs, key=lambda r: (order[r["status"]], r["name"].lower()))
counts = {c["id"]: sum(1 for r in rs if c["id"] in r["categories"]) for c in D["categories"]}
checked = dt.date.fromisoformat(D["last_checked"]); checked_txt = "%s %d, %d" % (MON[checked.month-1], checked.day, checked.year)

def card(r):
    a = r["address"]; addr = "%s, %s, %s %s" % (a["street"], a["city"], a["state"], a["zip"])
    cats = "".join('<span class="rs-cat">%s</span>' % E(CAT[c]) for c in r["categories"])
    hours_json = json.dumps(r["hours"], separators=(",", ":"))
    reopens = r.get("reopens") or ""
    reopens_text = dshort(reopens) if re.match(r"^\d{4}-", reopens) else reopens
    status_txt = {"open":"See hours","closed_for_season":"Closed for the season","temporarily_closed":"Temporarily closed","preorder_only":"Pre-order only"}[r["status"]]
    badge_cls = "rs-b-open" if r["status"] == "open" else "rs-b-closed" if "closed" in r["status"] else "rs-b-unknown"
    parts = ['<li class="rs" id="%s" data-cats="%s" data-status="%s" data-hours=\'%s\' data-reopens="%s" data-reopens-text="%s" data-search="%s" style="border-left-color:%s">'
             % (r["id"], " ".join(r["categories"]), r["status"], E(hours_json, quote=False), E(reopens), E(reopens_text),
                E((r["name"] + " " + " ".join(CAT[c] for c in r["categories"]) + " " + " ".join(r.get("tags", []))).lower()), COLORS[r["categories"][0]])]
    parts.append('<div class="rs-top"><div><h3>%s</h3><div class="rs-cats">%s</div></div><span class="rs-badge rs-state %s">%s</span></div>'
                 % ((('<a href="%s" target="_blank" rel="noopener">%s</a>' % (E(site(r)), E(r["name"]))) if site(r) else E(r["name"])), cats, badge_cls, E(status_txt)))
    parts.append('<p class="rs-today"></p>')
    if r.get("season_note"): parts.append('<p class="rs-note"><span class="rs-badge rs-b-season">Seasonal</span> %s</p>' % E(r["season_note"]) if r["seasonal"] else '<p class="rs-note">%s</p>' % E(r["season_note"]))
    parts.append('<p class="rs-addr"><a href="%s" target="_blank" rel="noopener">%s</a></p>' % (E(r["maps_url"]), E(addr)))
    links = ['<a href="tel:+1%s">Call %s</a>' % (re.sub(r"\D", "", r["phone"]), E(r["phone"]))]
    if site(r):
        lbl = {"official":"Website","facebook":"Facebook page","ordering":"Menu and ordering"}.get(r["website_type"], "Website")
        links.append('<a href="%s" target="_blank" rel="noopener">%s</a>' % (E(site(r)), lbl))
    parts.append('<p class="rs-contact">%s</p>' % "".join(links))
    low = r["hours_confidence"] == "low" or any(v is None for v in r["hours"].values())
    summ = "Hours for the week" if not low else "Hours (call ahead to confirm)"
    body = '<table><tbody>%s</tbody></table>' % rows(r)
    note = r.get("hours_text") or ""
    if r["status"] != "open" or low: body = '<p class="rs-note%s">%s</p>%s' % (" rs-low" if low else "", E(note), body if any(r["hours"][d] for d in DAYS) or any(v is None for v in r["hours"].values()) else "")
    if r.get("hours_note") and r["status"] == "open": body += '<p class="rs-note">%s</p>' % E(r["hours_note"])
    parts.append('<details><summary>%s</summary>%s</details>' % (summ, body))
    parts.append('<p class="rs-checked">Hours checked %s. Source: %s.</p>' % (E(dshort(r["hours_checked"])), E(r["hours_source"]["type"].split(" (")[0].split(" +")[0])))
    parts.append('</li>')
    return "".join(parts)

chips = ['<button type="button" class="rs-chip" aria-pressed="true" data-f="all" data-label="All">All<span class="rs-n">%d</span></button>' % len(rs)]
for c in D["categories"]:
    chips.append('<button type="button" class="rs-chip" aria-pressed="false" data-f="%s" data-label="%s" style="--cat:%s"><span class="rs-dot" aria-hidden="true"></span>%s<span class="rs-n">%d</span></button>'
                 % (c["id"], E(c["label"]), COLORS[c["id"]], E(c["label"]), counts[c["id"]]))

main = """  <section class="page-head"><div class="wrap narrow">
    <p class="eyebrow">Wolfeboro, New Hampshire</p>
    <h1>Places to eat in Wolfeboro</h1>
    <p class="sub">Hours last checked %s.</p>
    <p class="ev-intro">Every restaurant, cafe, bakery and ice cream stop we can find in Wolfeboro, with a link to each one. Pick a type to narrow the list, or switch on Open now. Hours change with the season here, so we recheck them every week and show the date on each listing.</p>
    <p class="toc">Spot a mistake or a place we missed? <a href="mailto:info@wolfeboroevents.com?subject=Wolfeboro%%20places%%20to%%20eat%%20correction">Email us</a> and we will fix it.</p>
  </div></section>
  <section class="rs-sec"><div class="rs-wrap">
    <div class="rs-tools" hidden>
      <div class="rs-row" role="group" aria-label="Show places by type">%s</div>
      <div class="rs-row" style="margin-top:8px"><button type="button" class="rs-chip rs-open" id="rs-open" aria-pressed="false">Open now</button></div>
      <div class="rs-search"><label class="ev-sr" for="rs-q">Search by name or food</label><input id="rs-q" type="search" placeholder="Search by name or food, like sushi" autocomplete="off"></div>
    </div>
    <p class="rs-meta" id="rs-count" aria-live="polite">%d places</p>
    <ul class="rs-list">%s</ul>
    <p class="rs-empty" id="rs-none" hidden>Nothing matches that. Try another type, or turn off Open now.</p>
    <p class="rs-fix">Listings are not endorsements, and nobody pays to be here. Winter hours can change with weather and holidays, so call ahead if it matters.</p>
  </div></section>
""" % (E(checked_txt), "".join(chips), len(rs), "".join(card(r) for r in rs))

# JSON-LD
def spec(r):
    if r["status"] != "open" or any(v is None for v in r["hours"].values()) or r["hours_confidence"] == "low": return None
    out = []
    for d in DAYS:
        for a, b in r["hours"][d]:
            out.append({"@type": "OpeningHoursSpecification", "dayOfWeek": DAYN[d], "opens": a, "closes": b})
    return out
items = []
for i, r in enumerate(rs, 1):
    a = r["address"]
    o = {"@type": "Restaurant", "name": r["name"], "telephone": "+1" + re.sub(r"\D", "", r["phone"]),
         "address": {"@type": "PostalAddress", "streetAddress": a["street"], "addressLocality": a["city"], "addressRegion": "NH", "postalCode": a["zip"], "addressCountry": "US"},
         "servesCuisine": [CAT[c] for c in r["categories"]]}
    if site(r): o["url"] = site(r)
    s = spec(r)
    if s: o["openingHoursSpecification"] = s
    items.append({"@type": "ListItem", "position": i, "item": o})
ld = {"@context": "https://schema.org", "@graph": [
  {"@type": "CollectionPage", "@id": "https://wolfeboroevents.com/restaurants/#webpage", "name": "Places to Eat in Wolfeboro, NH", "url": "https://wolfeboroevents.com/restaurants/", "dateModified": D["last_checked"]},
  {"@type": "ItemList", "name": "Wolfeboro NH restaurants, cafes and bakeries", "numberOfItems": len(rs), "itemListElement": items}]}
TITLE = "Wolfeboro NH Restaurants and Places to Eat | Wolfeboro Events"
DESC = "Every restaurant, cafe, bakery and ice cream stop in Wolfeboro, NH. Filter by pizza, seafood, breakfast and more, see who is open now, with hours checked weekly."

tpl = (ROOT / "scripts" / "restaurants_template.html").read_text(encoding="utf-8")
page = (tpl.replace("{{TITLE_H}}", E(TITLE)).replace("{{DESC_H}}", E(DESC))
           .replace("{{LD}}", json.dumps(ld, ensure_ascii=False).replace("</", "<\\/"))
           .replace("{{MAIN}}", main))
assert "{{" not in page
assert "\u2014" not in page and "\u2013" not in page, "em or en dash found"
assert not any(b in page for b in BANNED)
assert "wolfeborostays" not in page
out = ROOT / "restaurants" / "index.html"
out.parent.mkdir(exist_ok=True)
out.write_text(page, encoding="utf-8")
print("restaurants: %d places" % len(rs))
