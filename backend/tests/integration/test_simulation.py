"""Simulation, allocation and recommendation: CA-06 to CA-09, RM-1 to RM-6, FR-17, FR-19, NFR-01."""

import time

import pytest

from tests.conftest import add_storage, analyze, create_lot, reference, simulate


def _setup(client, auth, capacity=200.0, **lot):
    add_storage(client, auth, capacity)
    created = create_lot(client, auth, **lot)
    return created, analyze(client, auth, created["id"])


def _absorption(client, auth, code, kg):
    _, markets = reference(client, auth)
    return {"assumptions": {"markets": {markets[code]["id"]: {"absorption_kg": kg}}}}


def test_ca06_at_least_four_scenarios_with_quantiles(client, auth):
    _, a = _setup(client, auth)
    s = simulate(client, auth, a["id"])
    feasible = [sc for sc in s["scenarios"] if sc["feasible"]]
    assert len(feasible) >= 4
    for sc in feasible:
        for field in ("recoverable_kg", "net_value_fcfa", "loss"):
            q = sc[field]
            assert q["p10"] <= q["p50"] <= q["p90"]
    actions = {sc["action"] for sc in s["scenarios"]}
    assert {"continue", "store", "reroute", "sell_local"} <= actions
    assert s["disclaimer_code"] == "MODEL_ESTIMATE_NOT_FIELD_VALIDATED"
    assert any(item["key"] == "position" for item in s["assumptions"])


def test_ca07_storage_capacity_and_mass_conservation(client, auth):
    _, a = _setup(client, auth, capacity=200.0)
    s = simulate(client, auth, a["id"], **_absorption(client, auth, "M01", 250))
    store = next(sc for sc in s["scenarios"] if sc["action"] == "store")
    assert store["feasible"] is False and store["infeasible_reason"] == "STORAGE_CAPACITY_BELOW_LOT"
    split = next(sc for sc in s["scenarios"] if sc["action"] == "optimized_split")
    total = sum(line["kg"] for line in split["allocation"]) + split["discarded_kg"]
    assert total == pytest.approx(500.0, abs=1e-3)  # RM-1
    stored = sum(line["kg"] for line in split["allocation"] if line["action"] == "store")
    assert stored <= 200.0 + 1e-6  # RM-2
    assert len(split["allocation"]) >= 2


def test_t05_no_storage_site_means_store_unavailable_with_reason(client, auth):
    lot = create_lot(client, auth)
    s = simulate(client, auth, analyze(client, auth, lot["id"])["id"])
    store = [sc for sc in s["scenarios"] if sc["action"] == "store"]
    assert len(store) == 1 and not store[0]["feasible"]
    assert store[0]["infeasible_reason"] == "NO_STORAGE_SITE"


def test_ca08_recommendation_is_the_best_risk_adjusted_option(client, auth):
    _, a = _setup(client, auth, temp_override_c=24, harvested_at="2026-10-02T20:00:00Z")
    s = simulate(client, auth, a["id"])
    reco = s["recommendation"]
    compared = [sc for sc in s["scenarios"] if sc["feasible"] and not sc["discouraged"]] or [
        sc for sc in s["scenarios"] if sc["feasible"]
    ]
    lam = reco["policy"]["lam"]

    def score(sc):
        n = sc["net_value_fcfa"]
        return n["p50"] - lam * (n["p50"] - n["p10"])

    best = max(compared, key=score)
    if reco["no_clear_winner"]:
        assert reco["best_scenario_id"] is None and len(reco["candidate_scenario_ids"]) == 2
    else:
        assert reco["best_scenario_id"] == best["id"]
        assert reco["confidence"] in {"high", "medium", "low"}
    assert sum(sc["prob_best"] for sc in compared) == pytest.approx(1.0, abs=1e-6)
    same = client.get(f"/api/v1/simulations/{s['id']}/recommendation", headers=auth).json()
    assert same == reco


def test_lot_past_shelf_life_gets_least_bad_option_with_warning(client, auth):
    _, a = _setup(client, auth)
    assert a["shelf_life_p50_h"] == 0.0
    s = simulate(client, auth, a["id"])
    reco = s["recommendation"]
    assert reco["best_scenario_id"] is not None and reco["confidence"] == "low"
    assert reco["rationale_codes"][:2] == [
        "ALL_OPTIONS_DISCOURAGED",
        "HEAVY_LOSSES_LIKELY",
    ]
    assert all(sc["discouraged"] for sc in s["scenarios"] if sc["feasible"])


def test_ca09_same_inputs_and_seed_give_identical_outputs(client, auth):
    _, a = _setup(client, auth)
    first = simulate(client, auth, a["id"], seed=7, n_draws=1000)
    second = simulate(client, auth, a["id"], seed=7, n_draws=1000)
    strip = lambda s: [
        (sc["key"], sc["net_value_fcfa"], sc["prob_best"], sc["allocation"]) for sc in s["scenarios"]
    ]
    assert strip(first) == strip(second)
    other = simulate(client, auth, a["id"], seed=8, n_draws=1000)
    assert strip(other) != strip(first)


def test_fr17_user_assumptions_are_applied_and_flagged(client, auth):
    _, a = _setup(client, auth)
    base = simulate(client, auth, a["id"])
    _, markets = reference(client, auth)
    changed = simulate(
        client,
        auth,
        a["id"],
        risk_profile="prudent",
        assumptions={
            "markets": {markets["M01"]["id"]: {"price_fcfa_kg": 900}},
            "hold_h": 12,
            "surplus_price_fraction": 0.3,
        },
    )
    flags = {item["key"]: item for item in changed["assumptions"]}
    assert flags["price_fcfa_kg:M01"]["value"] == 900 and flags["price_fcfa_kg:M01"]["user_override"]
    assert flags["hold_h"]["value"] == 12 and flags["surplus_price_fraction"]["user_override"]
    assert changed["recommendation"]["policy"]["risk_profile"] == "prudent"
    cont = lambda s: next(sc for sc in s["scenarios"] if sc["key"] == "continue:M01")
    assert cont(changed)["net_value_fcfa"]["p50"] > cont(base)["net_value_fcfa"]["p50"]
    unknown = client.post(
        f"/api/v1/analyses/{a['id']}/simulations",
        headers=auth,
        json={"assumptions": {"markets": {"00000000-0000-0000-0000-000000000000": {"price_fcfa_kg": 1}}}},
    )
    assert unknown.status_code == 422


def test_simulation_input_bounds(client, auth):
    _, a = _setup(client, auth)
    for body in (
        {"n_draws": 50},
        {"n_draws": 50_000},
        {"seed": -1},
        {"risk_profile": "yolo"},
        {"assumptions": {"hold_h": 500}},
    ):
        assert (
            client.post(f"/api/v1/analyses/{a['id']}/simulations", headers=auth, json=body).status_code == 422
        )


def test_nfr01_analysis_and_simulation_under_three_seconds(client, auth):
    add_storage(client, auth)
    lot = create_lot(client, auth)
    started = time.perf_counter()
    a = analyze(client, auth, lot["id"])
    simulate(client, auth, a["id"], n_draws=2000)
    assert time.perf_counter() - started < 3.0


def test_fr19_sensitivity_grid(client, auth):
    _, a = _setup(client, auth, temp_override_c=24, harvested_at="2026-10-02T20:00:00Z")
    s = simulate(client, auth, a["id"])
    r = client.post(
        f"/api/v1/simulations/{s['id']}/sensitivity",
        headers=auth,
        json={"temperatures_c": [20, 28, 36], "delays_h": [0, 12, 24]},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["points"]) == 9
    for t in body["transitions"]:
        assert t["axis"] in {"temperature", "delay"} and t["from_action"] != t["to_action"]
    bad = client.post(
        f"/api/v1/simulations/{s['id']}/sensitivity",
        headers=auth,
        json={"temperatures_c": [20]},
    )
    assert bad.status_code == 422


def test_closed_lot_cannot_be_reanalysed(client, auth):
    lot, a = _setup(client, auth)
    s = simulate(client, auth, a["id"])
    client.post(
        f"/api/v1/lots/{lot['id']}/outcomes",
        headers=auth,
        json={
            "simulation_id": s["id"],
            "decision_taken": "continue",
            "actual_recovered_kg": 300,
            "actual_revenue_fcfa": 150000,
        },
    )
    assert client.post(f"/api/v1/lots/{lot['id']}/analyses", headers=auth, json={}).status_code == 409
    assert client.post(f"/api/v1/analyses/{a['id']}/simulations", headers=auth, json={}).status_code == 409
