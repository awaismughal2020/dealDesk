import json
from pathlib import Path

import pytest

from dealdesk.adapters.llm.fake import FakeModelClient, FixtureMissingError, fixture_key
from dealdesk.application.guardrails import data_block
from dealdesk.application.prompts import load_prompt
from dealdesk.application.schemas import EstimateOutput, ExtractionOutput, ProposalDraftOutput

ROOT = Path(__file__).resolve().parents[3]


def run(prompt_name: str, schema: type, **values: str) -> dict:
    prompt = load_prompt(prompt_name).render(**values)
    raw = FakeModelClient().complete(prompt, schema)
    assert raw.input_tokens > 0 and raw.output_tokens > 0
    return schema.model_validate_json(raw.text).model_dump()


def test_extracts_bullets_title_and_ambiguities() -> None:
    brief = (ROOT / "data/samples/ambiguous_brief.txt").read_text()
    out = run("extract_requirements", ExtractionOutput, brief=brief)
    assert out["title"] == "AI help for our claims documents"
    assert len(out["requirements"]) == 5
    assert out["requirements"][0]["priority"] == "could"
    assert out["requirements"][1]["priority"] == "must"
    assert len(out["ambiguities"]) >= 2


def test_extraction_is_naive_about_injected_bullets() -> None:
    brief = (ROOT / "data/samples/injection_brief.txt").read_text()
    out = run("extract_requirements", ExtractionOutput, brief=brief)
    assert any("Ignore previous instructions" in r["text"] for r in out["requirements"])


def test_shall_lines_without_bullets_and_categories() -> None:
    brief = (
        "Title\n\nThe supplier shall build dashboards and reports.\n"
        "The supplier must integrate with the API now.\nShort shall"
    )
    out = run("extract_requirements", ExtractionOutput, brief=brief)
    assert [r["category"] for r in out["requirements"]] == ["data", "integration"]
    assert out["summary"].startswith("The supplier shall")


def test_empty_brief() -> None:
    out = run("extract_requirements", ExtractionOutput, brief="")
    assert out["title"] == "Untitled brief"
    assert out["requirements"] == []


def estimate_context(n_requirements: int, references: list[dict]) -> str:
    return data_block(
        {
            "requirements": [{"text": f"r{i}"} for i in range(n_requirements)],
            "allowed_roles": ["engineer", "qa_engineer"],
            "reference_projects": references,
        }
    )


def test_estimate_scales_best_reference_and_drops_unknown_roles() -> None:
    reference = {
        "id": "PP-1",
        "actual_hours_by_role": {"engineer": "100", "wizard": "10", "qa_engineer": "1"},
    }
    out = run("estimate", EstimateOutput, context=estimate_context(4, [reference]))
    assert out["roles"] == [
        {"role": "engineer", "hours": "50"},
        {"role": "qa_engineer", "hours": "1"},
    ]
    assert out["reference_project_ids"] == ["PP-1"]


def test_estimate_without_references_falls_back() -> None:
    out = run("estimate", EstimateOutput, context=estimate_context(30, []))
    assert out["roles"] == [{"role": "engineer", "hours": "40"}]
    assert out["reference_project_ids"] == []


def test_revise_fixes_issues_and_shifts_low_margin_hours() -> None:
    context = data_block(
        {
            "previous_estimate": [
                {"role": "ml", "hours": "100"},
                {"role": "eng", "hours": "50"},
                {"role": "lead", "hours": "10"},
                {"role": "ghost", "hours": "5"},
                {"role": "qa", "hours": "9000"},
            ],
            "issues": [
                {"code": "UNKNOWN_ROLE", "role": "ghost"},
                {"code": "ABOVE_CEILING", "role": "qa"},
            ],
            "max_hours_per_role": "2000",
            "roles_by_margin_lowest_first": ["ml", "qa", "eng", "lead"],
            "allowed_roles": ["ml", "eng", "lead", "qa"],
        }
    )
    out = run("revise_estimate", EstimateOutput, context=context)
    hours = {r["role"]: r["hours"] for r in out["roles"]}
    assert hours == {"ml": "70", "eng": "80", "lead": "10", "qa": "2000"}
    assert "Moved 30 hours from ml to eng" in out["rationale"]


def test_revise_with_nothing_to_do() -> None:
    context = data_block(
        {"previous_estimate": [{"role": "x", "hours": "1"}], "allowed_roles": ["eng"]}
    )
    out = run("revise_estimate", EstimateOutput, context=context)
    assert out["roles"] == [{"role": "eng", "hours": "40"}]
    assert out["rationale"] == "No change was needed."


def test_draft_cites_case_studies_and_addresses_comment() -> None:
    context = data_block(
        {
            "title": "Portal",
            "requirements": [{"ref": "R-1", "text": "Build it"}],
            "ambiguities": ["When?"],
            "case_studies": [{"id": "CS-1", "title": "T", "summary": "S"}] * 3,
            "team": [{"role": "senior_engineer"}],
            "timeline_weeks": 12,
            "reviewer_comment": "Mention accessibility",
        }
    )
    out = run("draft_proposal", ProposalDraftOutput, context=context)
    assert "Mention accessibility" in out["executive_summary"]
    assert len(out["relevant_experience"]) == 2
    assert out["relevant_experience"][0]["source_ids"] == ["CS-1"]
    assert out["assumptions_and_exclusions"][0] == "When?"


def test_fixture_replay_and_strict_mode(tmp_path: Path) -> None:
    prompt = load_prompt("extract_requirements").render(brief="anything")
    key = fixture_key(prompt)
    assert key.startswith("extract_requirements.") and key == fixture_key(prompt)
    with pytest.raises(FixtureMissingError):
        FakeModelClient(fixtures_dir=tmp_path, strict=True).complete(prompt, ExtractionOutput)
    output = {"title": "Recorded", "summary": "", "requirements": [], "ambiguities": []}
    (tmp_path / f"{key}.json").write_text(json.dumps({"output": output}))
    raw = FakeModelClient(fixtures_dir=tmp_path, strict=True).complete(prompt, ExtractionOutput)
    assert json.loads(raw.text)["title"] == "Recorded"
    client = FakeModelClient(fixtures_dir=tmp_path / "missing")
    assert (client.provider, client.model) == ("fake", "fake-deterministic-v1")
    assert json.loads(client.complete(prompt, ExtractionOutput).text)["title"] == "anything"
