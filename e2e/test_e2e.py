"""End-to-end scenarios of the design document (E2E-1, E2E-3, E2E-4, E2E-5) in a real browser."""

from __future__ import annotations

import re

from conftest import BASE_URL, create_example_lot, register
from playwright.sync_api import Page, expect


def test_unauthenticated_visit_redirects_to_sign_in(page: Page):
    page.goto(f"{BASE_URL}/history")
    page.wait_for_url(re.compile(r"/login\?next=%2Fhistory"))
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible()


def test_nominal_flow_from_lot_to_recommendation(page: Page):
    """E2E-1 and E2E-3: lot -> risk band -> scenarios -> recommendation with a checked explanation."""
    register(page)
    create_example_lot(page)
    expect(page.locator(".gauge__caption")).to_contain_text("Likely value loss between")
    expect(page.locator(".facts")).to_contain_text("Air temperature")

    page.get_by_role("button", name="Compare decisions").click()
    page.wait_for_url("**/simulation")
    page.get_by_role("button", name="Simulate the decisions").click()
    expect(page.locator(".scenario").first).to_be_visible(timeout=30_000)
    expect(page.locator(".scenario--best")).to_have_count(1)
    expect(page.locator(".chart__row").first).to_be_visible()
    expect(page.locator(".assumption-list")).to_contain_text(
        "Air temperature on the route"
    )

    page.get_by_role("button", name="See the recommendation").click()
    page.wait_for_url("**/recommendation")
    banner = page.locator(".banner")
    expect(banner.first).to_be_visible()
    explanation = page.locator(".explanation__body")
    expect(explanation).to_be_visible(timeout=30_000)
    # Every figure of the explanation comes from the simulation: the banner's central value is in it.
    net = page.locator(".banner__value").inner_text().split(" FCFA")[0]
    expect(explanation).to_contain_text(net)
    expect(page.locator(".disclaimer")).to_contain_text("not a guarantee")
    assert not page.errors  # type: ignore[attr-defined]


def test_changed_assumption_is_flagged_and_replayed(page: Page):
    """FR-17: a user override is applied to the next simulation and labelled as such."""
    register(page)
    create_example_lot(page)
    page.get_by_role("button", name="Compare decisions").click()
    page.get_by_role("button", name="Simulate the decisions").click()
    expect(page.locator(".scenario").first).to_be_visible(timeout=30_000)
    page.get_by_role("button", name="Change the assumptions").click()
    page.get_by_label("Storage duration (h)").fill("12")
    page.get_by_role("button", name="Run again with these assumptions").click()
    expect(page.locator(".badge--manual").first).to_be_visible(timeout=30_000)


def test_decision_and_result_close_the_lot(page: Page):
    """E2E-5: the decision then the real result are recorded; the lot is closed and listed in history."""
    register(page)
    lot_id = create_example_lot(page)
    page.get_by_role("button", name="Compare decisions").click()
    page.get_by_role("button", name="Simulate the decisions").click()
    expect(page.locator(".scenario").first).to_be_visible(timeout=30_000)
    page.get_by_role("button", name="See the recommendation").click()
    page.get_by_role("button", name="I took this decision").click()
    expect(page.get_by_text("Decision recorded.")).to_be_visible()
    page.get_by_label("Quantity actually sold or recovered (kg)").fill("320")
    page.get_by_label("Actual revenue (FCFA)").fill("150000")
    page.get_by_role("button", name="Save the result").click()
    expect(page.get_by_text("Result saved. The lot is closed.")).to_be_visible()

    page.goto(f"{BASE_URL}/lots/{lot_id}/history")
    expect(page.locator(".outcomes")).to_contain_text("320 kg")
    page.goto(f"{BASE_URL}/history")
    page.get_by_label("Closed only").check()
    expect(page.locator(".lot-row")).to_have_count(1)


def test_weather_fallback_is_announced(page: Page):
    """When the automatic weather has no answer the form says which temperature will be assumed."""
    register(page)
    page.goto(f"{BASE_URL}/lots/new?example=1")
    expect(page.locator("input[name=quantity_kg]")).to_have_value("500")
    enrich = page.locator(".enrich")
    expect(enrich).not_to_contain_text("Checking", timeout=15_000)
    text = enrich.inner_text()
    assert "°C" in text and ("did not answer" in text or "automatic weather" in text)


def test_mobile_360px_has_no_horizontal_scroll(mobile: Page):
    """E2E-4: every main screen fits a 360 px wide phone."""
    register(mobile)
    lot_id = create_example_lot(mobile)
    widths = {}
    for path in [
        "/",
        "/lots/new",
        f"/lots/{lot_id}/analysis",
        "/history",
        "/assumptions",
        "/admin",
    ]:
        mobile.goto(f"{BASE_URL}{path}")
        mobile.wait_for_load_state("networkidle")
        widths[path] = mobile.evaluate("document.documentElement.scrollWidth")
    assert all(w <= 360 for w in widths.values()), widths
    mobile.get_by_role("button", name="Menu").click()
    expect(mobile.get_by_role("link", name="Assumptions", exact=True)).to_be_visible()


def test_question_about_the_analysis_is_simulated(page: Page):
    """FR-18: a "what if" question is answered by the simulation engine."""
    register(page)
    create_example_lot(page)
    page.get_by_role("button", name="Compare decisions").click()
    page.get_by_role("button", name="Simulate the decisions").click()
    expect(page.locator(".scenario").first).to_be_visible(timeout=30_000)
    page.get_by_role("button", name="See the recommendation").click()
    page.get_by_label("Your question").fill("What if the delay were 24 hours?")
    page.get_by_role("button", name="Ask", exact=True).click()
    answer = page.locator(".ask__answer").first
    expect(answer).to_contain_text("With a 24 h delay", timeout=30_000)
    expect(answer).to_contain_text("This test is not saved")
    expect(answer).not_to_contain_text("- FCFA")


def test_admin_market_value_is_used_in_the_form(page: Page):
    """FR-20: the organization's price for a market replaces the reference price."""
    register(page)
    page.goto(f"{BASE_URL}/admin")
    row = page.locator(".market-row", has_text="Marche Mboppi")
    row.get_by_label("Your price (FCFA/kg)").fill("640")
    row.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Market values saved.")).to_be_visible()
    create_example_lot(page)
    expect(page.locator(".facts")).to_contain_text("640")
    expect(page.locator(".facts")).to_contain_text("your organization's value")
