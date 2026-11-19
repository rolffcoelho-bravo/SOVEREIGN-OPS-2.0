"""API endpoint tests — synthetic fixtures only."""

from fastapi.testclient import TestClient

from sovereign_ops.api import create_app


def test_liveness_reports_g2_stage() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/live")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "alive"
        assert body["stage"] == "G2"
        assert body["mode"] == "RESEARCH_ONLY"
        assert body["inference"] == "NOT_IMPLEMENTED"


def test_liveness_rejects_post() -> None:
    with TestClient(create_app()) as client:
        assert client.post("/health/live").status_code == 405


def test_readiness_reports_registry_status() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in ("ready", "not_ready")
        assert isinstance(body["registry_loaded"], bool)
        if body["status"] == "ready":
            assert body["registry_sha256"] is not None
            assert body["datasets_registered"] >= 1


def test_provenance_returns_registered_datasets() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/provenance/registry")
        if response.status_code == 200:
            body = response.json()
            assert len(body["registry_sha256"]) == 64
            assert body["schema_version"] == "1"
            assert len(body["datasets"]) == 2
            ids = {d["dataset_id"] for d in body["datasets"]}
            assert ids == {"ESA-AD-v2", "EDP-SCADA-v2"}


def test_gates_endpoint_returns_development_progress() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/meta/gates")
        assert response.status_code == 200
        body = response.json()
        assert body["current_gate"] == "G2"
        assert len(body["gates"]) == 10
        gate_ids = [g["gate"] for g in body["gates"]]
        assert gate_ids == [f"G{i}" for i in range(10)]
        assert body["gates"][0]["status"] == "COMPLETE"
        assert body["gates"][1]["status"] == "COMPLETE"
        assert body["gates"][2]["status"] == "IN_PROGRESS"


def test_unimplemented_routes_return_404() -> None:
    with TestClient(create_app()) as client:
        assert client.post("/v1/analysis", json={}).status_code in (404, 405)
        assert client.post("/v1/cases", json={}).status_code in (404, 405)


def test_openapi_schema_includes_all_routes() -> None:
    with TestClient(create_app()) as client:
        doc = client.get("/openapi.json").json()
        paths = set(doc["paths"])
        assert "/health/live" in paths
        assert "/health/ready" in paths
        assert "/provenance/registry" in paths
        assert "/meta/gates" in paths
