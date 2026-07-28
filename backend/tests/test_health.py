import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

transport = ASGITransport(app=app)


@pytest.mark.asyncio
async def test_liveness_returns_request_id() -> None:
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-Id"].startswith("req_")


@pytest.mark.asyncio
async def test_contract_meta_reflects_confirmed_product_decisions() -> None:
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/meta/contracts")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["fixed_emotions"]) == 6
    assert payload["adjustment_limit_per_session"] == 3
    assert payload["retention_days_after_archive"] == 30
    assert payload["initial_structured_risk_classification"] is False
