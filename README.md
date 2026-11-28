# Wolfeboro Events

Standalone lightweight site for [wolfeboroevents.com](https://wolfeboroevents.com):
- `/`: Wolfeboro and Lakes Region events calendar (built from `data/events.json` via `scripts/events_component.py` with nightly auto-hide of past events and `/cal/*.ics` files)
- `/guide/`: Wolfeboro local guide
- `/outdoors/`: outdoor things to do within about an hour of Wolfeboro, built from `data/outdoors.json` by `scripts/build_outdoors.py` (also reused by wolfeborostays.com)
- `/restaurants/`: places to eat in Wolfeboro, built from `data/restaurants.json` by `scripts/build_restaurants.py` (template `scripts/restaurants_template.html`, assets in `assets/restaurants/`). Weekly hours updates are JSON-only edits: change `hours`, `hours_checked` and `hours_confidence` per place, plus the top-level `last_checked` (and the `/restaurants/` lastmod in `sitemap.xml`). A place with `website_check.status` of `unverified` is shown without a website link until the flag is cleared.
