#!/usr/bin/env python3
"""Build /outdoors/index.html from data/outdoors.json and scripts/outdoors_template.html.

data/outdoors.json is the source of truth; wolfeborostays.com reuses the built page's <main>.
Run before site_nav.py and apply_turnstile_pages.py (see netlify.toml)."""
import html, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
d = json.loads((ROOT / "data" / "outdoors.json").read_text(encoding="utf-8"))
tpl = (ROOT / "scripts" / "outdoors_template.html").read_text(encoding="utf-8")
E = html.escape
URL = "https://wolfeboroevents.com/outdoors/"

def card(i):
    out = ['<article class="od-card">',
           '<div class="od-head"><h3>%s</h3><span class="od-drive">%s</span></div>' % (E(i["name"]), E(i["drive"]))]
    if i.get("town"): out.append('<p class="od-town">%s</p>' % E(i["town"]))
    if i.get("stats"): out.append('<p class="od-stats">%s</p>' % E(i["stats"]))
    out.append('<p>%s</p>' % E(i["body"]))
    out.append('<p class="od-tip"><strong>Good to know:</strong> %s</p>' % E(i["tip"]))
    out.append('<p class="od-src">Details from <a href="%s" target="_blank" rel="noopener">%s</a></p>' % (E(i["source"][1]), E(i["source"][0])))
    out.append('</article>')
    return "".join(out)

toc = " · ".join('<a href="#%s">%s</a>' % (s["id"], E(s["title"])) for s in d["sections"])
parts = ['  <section class="page-head"><div class="wrap">',
         '    <p class="eyebrow">%s</p>' % E(d["eyebrow"]),
         '    <h1>%s</h1>' % E(d["h1"]),
         '    <p class="sub">%s</p>' % E(d["intro"]),
         '    <p class="toc">%s · <a href="#tips">Tips</a></p>' % toc,
         '  </div></section>']
for s in d["sections"]:
    parts.append('<section class="od-sec" id="%s"><div class="wrap"><h2 class="section-title">%s</h2><p class="lede">%s</p><div class="od-grid">%s</div></div></section>'
                 % (s["id"], E(s["title"]), E(s["lede"]), "".join(card(i) for i in s["items"])))
parts.append('<section class="od-sec" id="tips"><div class="wrap"><h2 class="section-title">%s</h2><ul class="od-tips">%s</ul><p class="footnote" style="margin-top:1.2rem;">%s</p></div></section>'
             % (E(d["tips_title"]), "".join("<li>%s</li>" % E(t) for t in d["tips"]), d["closing"]))
main = "\n".join(parts)

items = [i for s in d["sections"] for i in s["items"]]
ld = {"@context": "https://schema.org", "@graph": [
    {"@type": "WebPage", "@id": URL + "#webpage", "name": d["title"], "description": d["description"], "url": URL, "inLanguage": "en-US", "dateModified": d["updated"]},
    {"@type": "ItemList", "name": "Outdoor things to do near Wolfeboro", "itemListElement": [
        {"@type": "ListItem", "position": n + 1, "item": {"@type": "TouristAttraction", "name": i["name"], "url": i["source"][1]}} for n, i in enumerate(items)]}]}

page = (tpl.replace("{{TITLE_H}}", E(d["title"] + " | Wolfeboro Events"))
           .replace("{{DESC_H}}", E(d["description"]))
           .replace("{{LD}}", json.dumps(ld, ensure_ascii=False).replace("</", "<\\/"))
           .replace("{{MAIN}}", main))
assert "{{" not in page
out = ROOT / "outdoors" / "index.html"
out.parent.mkdir(exist_ok=True)
out.write_text(page, encoding="utf-8")
print("outdoors: %d items" % len(items))
