"""Runs over HTTP: the full flow, upload hardening, errors, headers, impact and the contract."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from docx import Document

from dealdesk.domain.models import UserRole
from scripts.export_openapi import openapi_document
from tests.integration.api.conftest import Api, start_sample_run
from tests.integration.api.pdfs import blank_pdf, encrypted_pdf, text_pdf

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]
BRIEF_LINES = [
    "SAMPLE RFP: Volunteer booking app (FICTIONAL)",
    "- The supplier shall build a booking web application for volunteers.",
    "- The app must send reminder notifications before each shift.",
    "- The supplier must provide an admin console for coordinators.",
    "- The app must integrate with our calendar system through its API.",
    "- The supplier shall carry out usability testing with volunteers.",
]


def test_full_flow_brief_to_approval_over_http(api: Api) -> None:
    estimator = api.as_role(UserRole.ESTIMATOR)
    run = start_sample_run(estimator)
    assert run["status"] in {"queued", "running", "awaiting_approval"}

    detail = estimator.get(f"/v1/runs/{run['id']}").json()
    assert detail["status"] == "awaiting_approval"
    assert detail["title"] == "Tenant self-service portal"
    assert detail["quote"]["price"] == "137830.00"
    assert detail["quote"]["target_price"] is not None
    assert len(detail["extraction"]["requirements"]) == 8
    assert detail["resource_plan"]["clashes"]
    assert detail["proposal"]["schedule"]["net_total"] == "137830.00"
    assert {s["step"] for s in detail["steps"]} >= {"intake", "estimate", "cost", "draft_proposal"}
    assert detail["actions"]["can_decide"] is False  # estimators never decide

    listing = estimator.get("/v1/runs", params={"status": "awaiting_approval"}).json()
    assert listing["total"] == 1
    assert listing["items"][0]["price"] == "137830.00"

    draft = estimator.get(f"/v1/runs/{run['id']}/proposal.docx")
    assert draft.status_code == 200
    assert draft.headers["content-type"].endswith("wordprocessingml.document")
    assert "DRAFT" in draft.headers["content-disposition"]
    assert (
        "DRAFT, requires approval"
        in Document(io.BytesIO(draft.content)).sections[0].header.paragraphs[0].text
    )

    approver = api.as_role(UserRole.APPROVER)
    approved = approver.post(
        f"/v1/runs/{run['id']}/approve", json={"comment": "Within policy"}
    ).json()
    assert approved["status"] == "approved"
    assert approved["is_final"] is True
    assert approved["pipeline_record"]["value"] == "137830.00"
    assert [m["net"] for m in approved["invoice_schedule"]["milestones"]] == [
        "41349.00",
        "55132.00",
        "41349.00",
    ]
    assert approved["approvals"][0]["comment"] == "Within policy"
    final = approver.get(f"/v1/runs/{run['id']}/proposal.docx")
    assert "FINAL" in final.headers["content-disposition"]


def test_injection_brief_is_flagged_and_priced_like_the_clean_one(api: Api) -> None:
    estimator = api.as_role(UserRole.ESTIMATOR)
    clean = estimator.get(f"/v1/runs/{start_sample_run(estimator)['id']}").json()
    attacked = estimator.get(
        f"/v1/runs/{start_sample_run(estimator, 'injection_brief')['id']}"
    ).json()
    assert "POSSIBLE_PROMPT_INJECTION" in attacked["flags"]
    assert len(attacked["extraction"]["quarantined"]) == 2
    assert attacked["quote"] == clean["quote"]


def test_rejection_returns_to_drafting_with_the_comment(api: Api) -> None:
    run = start_sample_run(api.as_role(UserRole.ESTIMATOR))
    approver = api.as_role(UserRole.APPROVER)
    rejected = approver.post(
        f"/v1/runs/{run['id']}/reject", json={"comment": "Add an accessibility audit"}
    ).json()
    assert rejected["status"] == "awaiting_approval"
    assert "Add an accessibility audit" in rejected["proposal"]["sections"]["executive_summary"]
    assert rejected["approvals"][0]["decision"] == "rejected"


def test_upload_text_pdf_is_accepted(api: Api) -> None:
    estimator = api.as_role(UserRole.ESTIMATOR)
    pdf = text_pdf(BRIEF_LINES * 2)
    response = estimator.post(
        "/v1/runs", files={"file": ("../../etc/brief?.pdf", pdf, "application/octet-stream")}
    )
    assert response.status_code == 202, response.text
    detail = estimator.get(f"/v1/runs/{response.json()['id']}").json()
    assert detail["brief_filename"] == "brief_.pdf"  # path stripped, unsafe characters replaced
    assert detail["status"] == "awaiting_approval"


@pytest.mark.parametrize(
    ("name", "content", "status", "message"),
    [
        ("locked.pdf", encrypted_pdf(BRIEF_LINES * 2), 422, "encrypted"),
        ("scan.pdf", blank_pdf(), 422, "scanned"),
        ("binary.txt", b"\x00\x01\x02" * 200, 415, "PDF or a UTF-8 text"),
        ("latin1.txt", "caf\xe9 ".encode("latin-1") * 100, 415, "PDF or a UTF-8 text"),
        ("short.txt", b"too short", 422, "too short"),
        ("empty.txt", b"", 422, "empty"),
        ("broken.pdf", b"%PDF-1.4 this is not really a pdf" * 20, 422, "could not be read"),
    ],
)
def test_upload_hardening(api: Api, name: str, content: bytes, status: int, message: str) -> None:
    estimator = api.as_role(UserRole.ESTIMATOR)
    response = estimator.post("/v1/runs", files={"file": (name, content, "application/pdf")})
    assert response.status_code == status, response.text
    assert message in response.json()["detail"]


def test_oversized_upload_is_rejected_before_parsing(api: Api) -> None:
    estimator = api.as_role(UserRole.ESTIMATOR)
    big = ("x" * 1023 + "\n").encode() * 200  # 200 KB > 64 KB test limit
    response = estimator.post("/v1/runs", files={"file": ("big.txt", big, "text/plain")})
    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"


def test_slightly_oversized_file_inside_body_limit_is_rejected(api: Api) -> None:
    estimator = api.as_role(UserRole.ESTIMATOR)
    content = (
        "y" * 99 + "\n"
    ).encode() * 700  # 70 KB: above the 64 KB file limit, below the body cap
    response = estimator.post("/v1/runs", files={"file": ("big.txt", content, "text/plain")})
    assert response.status_code == 413


def test_exactly_one_source_is_required(api: Api) -> None:
    estimator = api.as_role(UserRole.ESTIMATOR)
    neither = estimator.post("/v1/runs", data={})
    both = estimator.post(
        "/v1/runs",
        data={"sample_id": "clean_brief"},
        files={"file": ("a.txt", b"x" * 300, "text/plain")},
    )
    unknown = estimator.post("/v1/runs", data={"sample_id": "../secrets"})
    assert (neither.status_code, both.status_code, unknown.status_code) == (422, 422, 404)


def test_samples_listing(api: Api) -> None:
    items = api.as_role(UserRole.ESTIMATOR).get("/v1/samples").json()["items"]
    assert [i["id"] for i in items] == ["ambiguous_brief", "clean_brief", "injection_brief"]
    assert all("SAMPLE" in i["title"] for i in items)


def test_problem_json_security_headers_and_request_ids(api: Api) -> None:
    client = api.as_role(UserRole.VIEWER)
    response = client.get("/v1/runs", params={"limit": 0}, headers={"X-Request-ID": "trace-123"})
    assert response.status_code == 422
    body = response.json()
    assert response.headers["content-type"] == "application/problem+json"
    assert body["title"] == "Invalid request"
    assert body["request_id"] == "trace-123"
    assert body["errors"][0]["loc"] == "query.limit"
    assert response.headers["X-Request-ID"] == "trace-123"
    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"
    bad_id = client.get("/healthz", headers={"X-Request-ID": "bad id with spaces"})
    assert bad_id.headers["X-Request-ID"] != "bad id with spaces"
    assert client.get("/readyz").json() == {"status": "ready"}


def test_impact_defaults_and_recalculation(api: Api) -> None:
    viewer = api.as_role(UserRole.VIEWER)
    start_sample_run(api.as_role(UserRole.ESTIMATOR))
    impact = viewer.get("/v1/impact").json()
    assert impact["metrics"]["baseline_hours_per_bid"] == "40.00"
    assert "Assumptions, not measurements" in impact["metrics"]["notice"]
    assert "intake" in impact["measured_steps"]
    assumptions = impact["assumptions"]
    assumptions["bids_per_year"] = 120
    recalculated = viewer.post("/v1/impact/calculate", json=assumptions).json()
    assert recalculated["annual_hours_saved"] != impact["metrics"]["annual_hours_saved"]
    assumptions["cashable_share"] = "1.5"
    assert viewer.post("/v1/impact/calculate", json=assumptions).status_code == 422


def test_openapi_snapshot_is_current(api: Api) -> None:
    committed = json.loads((ROOT / "web" / "openapi.json").read_text(encoding="utf-8"))
    assert committed == openapi_document(api.app), "run `make gen-client` and commit the result"
