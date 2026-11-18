from fastapi.testclient import TestClient

from sovereign_ops.api import create_app


def test_liveness_does_not_claim_inference_readiness() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {
            "status": "alive",
            "stage": "G0",
            "mode": "RESEARCH_ONLY",
            "inference": "NOT_IMPLEMENTED",
        }
        assert client.get("/health/ready").status_code == 404
        assert client.post("/v1/analysis", json={}).status_code == 404
        assert client.post("/v1/cases", json={}).status_code == 404
        assert client.post("/health/live").status_code == 405


def test_openapi_exposes_only_implemented_health_route() -> None:
    with TestClient(create_app()) as client:
        document = client.get("/openapi.json").json()
        assert set(document["paths"]) == {"/health/live"}
        assert "LivenessResponse" in document["components"]["schemas"]
