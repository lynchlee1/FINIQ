from fastapi.testclient import TestClient

from finiq.market_desk.web.app import JOB_HANDLERS, app


def test_dart_link_workflow_is_not_exposed() -> None:
    client = TestClient(app)

    assert "dart_link" not in JOB_HANDLERS
    assert client.post("/api/disclosures/dart-links/build", json={}).status_code == 404
    assert (
        client.post("/api/disclosures/dart-links/build/start", json={}).status_code
        == 404
    )

