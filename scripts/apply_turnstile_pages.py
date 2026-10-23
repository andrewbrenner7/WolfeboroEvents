#!/usr/bin/env python3
"""Fill the Turnstile site key on the events and guide pages (run after the events build).
If TURNSTILE_SITE_KEY is not set, drop the widget so the form still works."""
import os, re, pathlib

def apply_turnstile(text):
    key = os.environ.get("TURNSTILE_SITE_KEY", "").strip()
    if key and re.fullmatch(r"[0-9A-Za-z_-]{8,64}", key):
        return text.replace("__TURNSTILE_SITE_KEY__", key)
    text = re.sub(r'[ \t]*<script src="https://challenges\.cloudflare\.com/turnstile/v0/api\.js"[^>]*></script>\n?', "", text)
    text = re.sub(r'[ \t]*<div class="cf-turnstile"[^>]*></div>\n?', "", text)
    return text

for path in ["index.html", "guide/index.html", "join/index.html"]:
    p = pathlib.Path(path)
    if p.exists():
        p.write_text(apply_turnstile(p.read_text(encoding="utf-8")), encoding="utf-8")
