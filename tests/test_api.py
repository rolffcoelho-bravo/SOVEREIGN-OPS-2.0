"""API endpoint tests — synthetic fixtures only."""

from fastapi.testclient import TestClient

from sovereign_ops.api import create_app


def test_liveness_reports_g3_stage() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/live")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "alive"
        assert body["stage"] == "G4"
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
        assert body["current_gate"] == "G4"
        assert len(body["gates"]) == 10
        gate_ids = [g["gate"] for g in body["gates"]]
        assert gate_ids == [f"G{i}" for i in range(10)]
        # G0, G1, G2 all COMPLETE
        assert body["gates"][0]["status"] == "COMPLETE"
        assert body["gates"][1]["status"] == "COMPLETE"
        assert body["gates"][2]["status"] == "COMPLETE"
        # G3 COMPLETE, G4 now IN_PROGRESS
        assert body["gates"][3]["status"] == "COMPLETE"
        assert body["gates"][4]["status"] == "IN_PROGRESS"


def test_unimplemented_routes_return_404() -> None:
    with TestClient(create_app()) as client:
        assert client.post("/v1/analysis", json={}).status_code in (404, 405)
        assert client.post("/v1/cases", json={}).status_code in (404, 405)


def test_quality_schemas_returns_all_schemas() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/quality/schemas")
        assert response.status_code == 200
        body = response.json()
        schemas = body["schemas"]
        assert len(schemas) == 3  # ESA, EDP SCADA, EDP failures
        ids = {s["dataset_id"] for s in schemas}
        assert ids == {"ESA-AD-v2", "EDP-SCADA-v2"}
        for s in schemas:
            assert len(s["sha256"]) == 64
            assert s["column_count"] == len(s["columns"])


def test_quality_schemas_by_dataset() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/quality/schemas/ESA-AD-v2")
        assert response.status_code == 200
        body = response.json()
        assert len(body["schemas"]) == 1
        assert body["schemas"][0]["dataset_id"] == "ESA-AD-v2"
        assert body["schemas"][0]["column_count"] == 4


def test_quality_schemas_unknown_dataset_404() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/quality/schemas/NONEXISTENT")
        assert response.status_code == 404


def test_pipeline_config_returns_defaults() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/pipeline/config")
        assert response.status_code == 200
        body = response.json()
        assert body["stage"] == "G4"
        assert body["default_train_frac"] == 0.6
        assert body["default_calibration_frac"] == 0.2
        assert body["default_test_frac"] == 0.2
        assert body["provenance_hash"] == "SHA-256"
        assert body["domain_isolation"] is True
        assert set(body["supported_domains"]) == {"ESA-AD-v2", "EDP-SCADA-v2"}


def test_decision_protocol_returns_policy_and_outcomes() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/pipeline/decision-protocol")
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "DARP Decision Protocol"
        assert body["confidence_formula"] == "coverage × f1"
        assert body["domain_isolation"] is True

        # Policy defaults
        policy = body["policy"]
        assert policy["min_coverage"] == 0.7
        assert policy["min_f1"] == 0.3
        assert policy["alert_confidence"] == 0.8
        assert policy["investigate_confidence"] == 0.5
        assert policy["max_abstention_rate"] == 0.5

        # Five outcomes in priority order
        outcomes = body["outcomes"]
        assert len(outcomes) == 5
        priorities = [o["priority"] for o in outcomes]
        assert priorities == [1, 2, 3, 4, 5]
        outcome_names = [o["outcome"] for o in outcomes]
        assert outcome_names == [
            "BLOCK_DATA_INTEGRITY",
            "DEGRADED_SERVICE",
            "ABSTAIN_INSUFFICIENT_EVIDENCE",
            "SUPPORTED_ALERT",
            "INVESTIGATE",
        ]
        # Actionable: only SUPPORTED_ALERT and INVESTIGATE
        actionable = [o["outcome"] for o in outcomes if o["actionable"]]
        assert actionable == ["SUPPORTED_ALERT", "INVESTIGATE"]


def test_openapi_schema_includes_all_routes() -> None:
    with TestClient(create_app()) as client:
        doc = client.get("/openapi.json").json()
        paths = set(doc["paths"])
        assert "/health/live" in paths
        assert "/health/ready" in paths
        assert "/provenance/registry" in paths
        assert "/meta/gates" in paths
        assert "/quality/schemas" in paths
        assert "/quality/schemas/{dataset_id}" in paths
        # G4 endpoints
        assert "/pipeline/config" in paths
        assert "/pipeline/decision-protocol" in paths
