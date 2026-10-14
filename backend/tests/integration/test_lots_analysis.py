"""Lots and risk analysis: CA-01 to CA-05, FR-03, FR-16."""

from datetime import UTC, datetime, timedelta

from tests.conftest import analyze, create_lot, demo_lot_payload


def test_ca01_create_lot_and_list_it(client, auth):
    lot = create_lot(client, auth)
    assert lot["status"] == "open" and lot["delay_h"] == 12.0
    assert lot["destination_city"] == "Douala"
    listed = client.get("/api/v1/lots", headers=auth).json()
    assert [item["id"] for item in listed["items"]] == [lot["id"]]
    assert (
        client.get(f"/api/v1/lots/{lot['id']}", headers=auth).json()["notes"] == "lot de la coopérative nord"
    )


def test_ca02_future_harvest_and_non_positive_quantity_are_field_errors(client, auth):
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    later = (datetime.now(UTC) + timedelta(days=4)).isoformat()
    r = client.post(
        "/api/v1/lots",
        headers=auth,
        json=demo_lot_payload(
            client,
            auth,
            harvested_at=future,
            eta_planned_at=later,
            eta_current_at=later,
        ),
    )
    assert r.status_code == 422
    assert r.json()["errors"] == [
        {
            "field": "harvested_at",
            "code": "future_date",
            "message": "harvest date cannot be in the future",
        }
    ]
    r = client.post("/api/v1/lots", headers=auth, json=demo_lot_payload(client, auth, quantity_kg=0))
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "quantity_kg"
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["request_id"]


def test_lot_validation_rules(client, auth):
    cases = [
        {"maturity": "rotten"},
        {"eta_planned_at": "2026-09-30T06:00:00Z"},
        {"harvested_at": "2026-10-01T06:00:00"},  # naive datetime refused
        {"temp_override_c": 60},
        {"notes": "x" * 501},
        {"unknown_field": 1},
    ]
    for override in cases:
        r = client.post(
            "/api/v1/lots",
            headers=auth,
            json=demo_lot_payload(client, auth, **override),
        )
        assert r.status_code == 422, override
    payload = demo_lot_payload(client, auth)
    payload["destination_market_id"] = payload["origin_location_id"]
    r = client.post("/api/v1/lots", headers=auth, json=payload)
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "destination_market_id"


def test_pagination_with_cursor(client, auth):
    ids = [create_lot(client, auth)["id"] for _ in range(3)]
    page = client.get("/api/v1/lots?limit=2", headers=auth).json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    rest = client.get(f"/api/v1/lots?limit=2&cursor={page['next_cursor']}", headers=auth).json()
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None
    assert {i["id"] for i in page["items"] + rest["items"]} == set(ids)
    assert client.get("/api/v1/lots?cursor=not-a-cursor", headers=auth).status_code == 422


def test_patch_lot(client, auth):
    lot = create_lot(client, auth)
    r = client.patch(
        f"/api/v1/lots/{lot['id']}",
        headers=auth,
        json={"eta_current_at": "2026-10-04T08:00:00Z", "temp_override_c": 31},
    )
    assert r.status_code == 200 and r.json()["delay_h"] == 18.0 and r.json()["temp_override_c"] == 31
    bad = client.patch(
        f"/api/v1/lots/{lot['id']}",
        headers=auth,
        json={"eta_current_at": "2026-09-01T00:00:00Z"},
    )
    assert bad.status_code == 422


def test_ca04_analysis_returns_ordered_quantiles_risk_and_factors(client, auth):
    lot = create_lot(client, auth)
    a = analyze(client, auth, lot["id"])
    q = a["risk"]["loss_fraction"]
    assert 0 <= q["p10"] <= q["p50"] <= q["p90"] <= 1
    assert a["risk"]["level"] in {"low", "medium", "high"}
    assert len(a["top_factors"]) >= 3
    contributions = [abs(f["contribution"]) for f in a["top_factors"]]
    assert contributions == sorted(contributions, reverse=True)
    assert a["inputs"]["age_h"] == 50.0 and a["inputs"]["remaining_transit_h"] == 18.0
    assert a["inputs"]["delay_h"] == 12.0
    assert a["replay"] is True and a["disclaimer_code"] == "MODEL_ESTIMATE_NOT_FIELD_VALIDATED"
    assert a["model"]["name"] == "kinetic"
    stored = client.get(f"/api/v1/analyses/{a['id']}", headers=auth).json()
    assert stored["risk"] == a["risk"]


def test_ca03_weather_unavailable_uses_labelled_default_and_preview_says_so(client, auth):
    lot = create_lot(client, auth)
    a = analyze(client, auth, lot["id"])
    assert a["inputs"]["temp_mean_c"]["source"].startswith("assumption")
    payload = demo_lot_payload(client, auth)
    r = client.post(
        "/api/v1/lots/enrichment-preview",
        headers=auth,
        json={
            "origin_location_id": payload["origin_location_id"],
            "destination_market_id": payload["destination_market_id"],
            "harvested_at": payload["harvested_at"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["temperature_available"] is False
    assert body["temperature"]["source"].startswith("assumption")
    assert body["route_km"]["value"] > 0 and body["suggested_eta_at"]
    assert body["price_fcfa_kg"]["value"] == 600


def test_ca05_hotter_lot_never_loses_less(client, auth):
    cool = create_lot(client, auth, temp_override_c=25)
    hot = create_lot(client, auth, temp_override_c=33)
    a_cool = analyze(client, auth, cool["id"])
    a_hot = analyze(client, auth, hot["id"])
    assert a_cool["inputs"]["temp_mean_c"] == {"value": 25.0, "source": "manual"}
    assert a_hot["risk"]["loss_fraction"]["p50"] >= a_cool["risk"]["loss_fraction"]["p50"]


def test_packaging_and_maturity_change_the_estimate(client, auth):
    crate = analyze(client, auth, create_lot(client, auth, temp_override_c=29)["id"])
    sack = analyze(
        client,
        auth,
        create_lot(client, auth, temp_override_c=29, packaging="sack")["id"],
    )
    assert sack["risk"]["loss_fraction"]["p50"] > crate["risk"]["loss_fraction"]["p50"]


def test_replay_and_analysis_time_rules(client, auth):
    lot = create_lot(client, auth)
    before = client.post(
        f"/api/v1/lots/{lot['id']}/analyses",
        headers=auth,
        json={"analysis_at": "2026-09-30T00:00:00Z"},
    )
    assert before.status_code == 422 and before.json()["errors"][0]["field"] == "analysis_at"
    early = analyze(client, auth, lot["id"], at="2026-10-01T12:00:00Z")
    late = analyze(client, auth, lot["id"], at="2026-10-03T20:00:00Z")
    assert early["inputs"]["age_h"] == 6.0
    assert late["risk"]["loss_fraction"]["p50"] >= early["risk"]["loss_fraction"]["p50"]
    detail = client.get(f"/api/v1/lots/{lot['id']}", headers=auth).json()
    assert detail["latest_analysis"]["id"] == late["id"]


def test_analysis_is_reproducible(client, auth):
    lot = create_lot(client, auth)
    a1 = analyze(client, auth, lot["id"])
    a2 = analyze(client, auth, lot["id"])
    assert a1["risk"] == a2["risk"] and a1["top_factors"] == a2["top_factors"]
