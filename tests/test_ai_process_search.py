"""Regression tests for the SIMO AI product/material retrieval path exposed
over HTTP (POST /api/v1/process -> BrainManager -> SearchAssistant ->
MaterialSearchService) — Sprint 032, Workstream B.

Public endpoint (ADR-023), so no auth header is needed here.
"""


def test_process_found_returns_canonical_material(client):
    r = client.post("/api/v1/process", json={"text": "Find Calacatta Gold 20mm"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "found"
    assert body["result"]["material"] == "Calacatta Gold"
    assert body["result"]["details"]["thickness"] == "20mm"


def test_process_multiple_returns_real_candidates_never_fabricated(client):
    r = client.post("/api/v1/process", json={"text": "Do we have Carrara?"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "multiple"
    names = {item["material"] for item in body["results"]}
    assert names == {"Carrara Mist", "Carrara White"}


def test_process_not_found_never_invents_a_product(client):
    r = client.post("/api/v1/process", json={"text": "Find SuperGalaxy Diamond Quartz"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_found"
    assert "message" in body


def test_process_category_search_returns_all_matching(client):
    r = client.post("/api/v1/process", json={"text": "Show me all available marble"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "multiple"
    assert all(item["details"]["category"] == "Marble" for item in body["results"])


def test_process_pricing_query_routes_to_sales_and_never_fabricates(client):
    r = client.post("/api/v1/process", json={"text": "How much is Nero Marquina 30mm?"})
    assert r.status_code == 200
    body = r.json()
    assert body["material"] == "Nero Marquina"
    assert body["details"]["thickness"] == "30mm"


def test_process_pricing_query_for_missing_material_never_fabricates_a_price(client):
    r = client.post("/api/v1/process", json={"text": "How much is SuperGalaxy Diamond Quartz?"})
    assert r.status_code == 200
    body = r.json()
    assert "material" not in body
    assert "price" not in body
    assert body["message"] == "I couldn't find that material."


def test_process_unmatched_keywords_still_finds_real_material_via_fallback(client):
    r = client.post("/api/v1/process", json={"text": "Carrara Mist please"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "multiple"
    names = {item["material"] for item in body["results"]}
    assert names == {"Carrara Mist"}


def test_process_partial_name_search(client):
    r = client.post("/api/v1/process", json={"text": "Find 20mm Calacatta products"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "multiple"
    names = {item["material"] for item in body["results"]}
    assert names == {"Calacatta Gold", "Calacatta Oro", "Calacatta Porcelain"}
    assert all(item["details"]["thickness"] == "20mm" for item in body["results"])
