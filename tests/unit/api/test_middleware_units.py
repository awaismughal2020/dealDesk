from fastapi import FastAPI
from fastapi.testclient import TestClient

from dealdesk.api.middleware import SecurityHeadersMiddleware


def app_with(hsts: bool) -> TestClient:
    app = FastAPI(docs_url="/docs")
    app.add_middleware(SecurityHeadersMiddleware, hsts=hsts)

    @app.get("/x")
    def x() -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(app)


def test_hsts_only_outside_local_and_docs_csp() -> None:
    assert "Strict-Transport-Security" not in app_with(hsts=False).get("/x").headers
    secure = app_with(hsts=True)
    assert secure.get("/x").headers["Strict-Transport-Security"].startswith("max-age=")
    docs = secure.get("/docs").headers["Content-Security-Policy"]
    assert "cdn.jsdelivr.net" in docs
    assert "frame-ancestors 'none'" in docs
