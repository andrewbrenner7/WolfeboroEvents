#!/usr/bin/env python3
"""Inject the shared top nav into built pages that contain <!-- site-nav -->.

Edit scripts/site_nav.json to add houses or links. Runs after the other build steps.
"""
import html, json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
cfg = json.loads((ROOT / "scripts" / "site_nav.json").read_text(encoding="utf-8"))
items = cfg["houses"] + cfg["links"]

for rel, here in cfg["pages"].items():
    page = ROOT / rel
    if not page.exists():
        continue
    links = "".join(
        '<a href="%s"%s>%s</a>' % (html.escape(i["href"]), ' aria-current="page"' if i["href"] == here else "", html.escape(i["label"]))
        for i in items)
    nav_html = '<nav class="nav-links" aria-label="Site">%s</nav>' % links
    text = page.read_text(encoding="utf-8")
    if "<!-- site-nav -->" in text:
        page.write_text(text.replace("<!-- site-nav -->", nav_html), encoding="utf-8")
        print("nav: %s" % rel)
    elif '<nav class="nav-links" aria-label="Site">' in text:
        page.write_text(re.sub(r'<nav class="nav-links" aria-label="Site">.*?</nav>', nav_html, text), encoding="utf-8")
        print("nav: %s" % rel)
