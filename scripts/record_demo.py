"""Record the public-hackathon demo flow against a running SALVA instance.

Usage:
  SALVA_URL=http://127.0.0.1:8000 python scripts/record_demo.py

The temporary account is created during the run and is not a real credential.
The browser video is converted to MP4 by the shell command that follows this script.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("SALVA_URL", "http://127.0.0.1:8000").rstrip("/")
OUT = Path(os.environ.get("DEMO_VIDEO_DIR", "artifacts/demo"))
OUT.mkdir(parents=True, exist_ok=True)
PASSWORD = "SALVA-demo-2026!"
EMAIL = f"video-{int(time.time())}-{uuid.uuid4().hex[:6]}@example.cm"


def hold(page, milliseconds: int = 1800) -> None:
    page.wait_for_timeout(milliseconds)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="en-GB",
        record_video_dir=str(OUT / "raw"),
        record_video_size={"width": 1280, "height": 800},
    )
    page = context.new_page()
    page.goto(f"{BASE_URL}/register")
    hold(page, 1700)
    page.get_by_label("Organization name").fill("SALVA demo cooperative")
    page.get_by_label("E-mail address").fill(EMAIL)
    page.get_by_label("Password", exact=True).fill(PASSWORD)
    hold(page, 900)
    page.get_by_role("button", name="Create an account").click()
    page.wait_for_url(f"{BASE_URL}/")
    hold(page, 1900)

    page.goto(f"{BASE_URL}/lots/new?example=1")
    page.get_by_label("Quantity (kg)").wait_for()
    hold(page, 2200)
    page.get_by_role("button", name="Create and analyse this lot").click()
    page.wait_for_url("**/lots/*/analysis")
    page.locator(".gauge").wait_for(timeout=30_000)
    hold(page, 3000)

    page.get_by_role("button", name="Compare decisions").click()
    page.wait_for_url("**/simulation")
    hold(page, 1800)
    page.get_by_role("button", name="Simulate the decisions").click()
    page.locator(".scenario").first.wait_for(timeout=30_000)
    hold(page, 4200)

    page.get_by_role("button", name="Change the assumptions").click()
    hold(page, 1800)
    page.get_by_label("Storage duration (h)").fill("12")
    page.get_by_role("button", name="Run again with these assumptions").click()
    page.locator(".badge--manual").first.wait_for(timeout=30_000)
    hold(page, 2800)

    page.get_by_role("button", name="See the recommendation").click()
    page.wait_for_url("**/recommendation")
    page.locator(".banner").first.wait_for()
    page.locator(".explanation__body").wait_for(timeout=30_000)
    hold(page, 4200)

    page.get_by_label("Your question").fill("What if the delay were 24 hours?")
    page.get_by_role("button", name="Ask", exact=True).click()
    page.locator(".ask__answer").first.wait_for(timeout=30_000)
    hold(page, 3500)

    page.goto(f"{BASE_URL}/assumptions")
    hold(page, 3500)
    context.close()
    browser.close()

videos = sorted((OUT / "raw").glob("*.webm"), key=lambda p: p.stat().st_mtime)
if not videos:
    raise SystemExit("No browser video was produced")
print(videos[-1])
