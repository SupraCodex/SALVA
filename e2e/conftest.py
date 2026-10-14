"""Browser tests against a running SALVA instance (API + built interface).

    SALVA_URL=http://127.0.0.1:8000 pytest e2e

The server must have the reference data seeded (python -m app.seed --reference). Each test
registers its own organization, so no shared credentials are needed.
"""

from __future__ import annotations

import os
import uuid

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

BASE_URL = os.environ.get("SALVA_URL", "http://127.0.0.1:8000").rstrip("/")


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        launch = (
            {"executable_path": os.environ["CHROMIUM_PATH"]}
            if os.environ.get("CHROMIUM_PATH")
            else {}
        )
        b = p.chromium.launch(**launch)
        yield b
        b.close()


def _page(browser: Browser, width: int, height: int) -> Page:
    context = browser.new_context(
        viewport={"width": width, "height": height}, locale="en-GB"
    )
    page = context.new_page()
    page.errors = []  # type: ignore[attr-defined]
    page.on("pageerror", lambda e: page.errors.append(str(e)))  # type: ignore[attr-defined]
    return page


@pytest.fixture
def page(browser):
    p = _page(browser, 1280, 860)
    yield p
    p.context.close()


@pytest.fixture
def mobile(browser):
    p = _page(browser, 360, 740)
    yield p
    p.context.close()


def register(page: Page) -> str:
    email = f"e2e-{uuid.uuid4().hex[:10]}@example.cm"
    page.goto(f"{BASE_URL}/register")
    page.get_by_label("Organization name").fill(f"E2E cooperative {email[4:14]}")
    page.get_by_label("E-mail address").fill(email)
    page.get_by_label("Password").fill("tomates-e2e-2026")
    page.get_by_role("button", name="Create an account").click()
    page.wait_for_url(f"{BASE_URL}/")
    return email


def create_example_lot(page: Page) -> str:
    """Create the demonstration lot through the form and wait for its risk analysis."""
    page.goto(f"{BASE_URL}/lots/new?example=1")
    page.get_by_label("Quantity (kg)").wait_for()
    expect(page.locator("input[name=quantity_kg]")).to_have_value("500")
    page.get_by_role("button", name="Create and analyse this lot").click()
    page.wait_for_url("**/lots/*/analysis")
    page.locator(".gauge").wait_for(timeout=30_000)
    return page.url.split("/lots/")[1].split("/")[0]
