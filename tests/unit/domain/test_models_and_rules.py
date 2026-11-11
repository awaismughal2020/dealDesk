import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

import dealdesk.domain
from dealdesk.domain.approval import ensure_separation_of_duties
from dealdesk.domain.errors import InvalidPolicyError, SeparationOfDutiesError
from dealdesk.domain.models import (
    AuditEvent,
    CostingPolicy,
    Estimate,
    RateCardEntry,
)

D = Decimal
DOMAIN_DIR = Path(dealdesk.domain.__file__).parent


@pytest.mark.parametrize(
    ("contingency", "target", "minimum", "ceiling"),
    [
        (D("-0.1"), D("0.3"), D("0.2"), D(10)),
        (D("1.1"), D("0.3"), D("0.2"), D(10)),
        (D("0.1"), D("0.2"), D("0.3"), D(10)),
        (D("0.1"), D(1), D("0.2"), D(10)),
        (D("0.1"), D("0.3"), D("-0.1"), D(10)),
        (D("0.1"), D("0.3"), D("0.2"), D(0)),
    ],
)
def test_costing_policy_guard_rails(
    contingency: Decimal, target: Decimal, minimum: Decimal, ceiling: Decimal
) -> None:
    with pytest.raises(InvalidPolicyError):
        CostingPolicy(contingency, target, minimum, ceiling)


@pytest.mark.parametrize(("cost", "sell"), [(D(-1), D(10)), (D(1), D("0.99"))])
def test_rate_card_entry_guard_rails(cost: Decimal, sell: Decimal) -> None:
    with pytest.raises(InvalidPolicyError):
        RateCardEntry("x", cost, sell)


def test_estimate_is_immutable_and_totals() -> None:
    source = {"a": D(1), "b": D("2.5")}
    estimate = Estimate(source)
    source["a"] = D(100)
    assert estimate.total_hours == D("3.5")
    with pytest.raises(TypeError):
        estimate.hours_by_role["a"] = D(5)  # type: ignore[index]


def test_separation_of_duties() -> None:
    creator = uuid4()
    ensure_separation_of_duties(uuid4(), creator)
    with pytest.raises(SeparationOfDutiesError):
        ensure_separation_of_duties(creator, creator)


def test_audit_event_defaults() -> None:
    event = AuditEvent("run.created", None, "run", "1", datetime.now(UTC))
    assert event.details == {}
    assert event.request_id is None


def _float_uses(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            found.append(f"{path.name}:{node.lineno} float literal {node.value!r}")
        elif isinstance(node, ast.Name) and node.id == "float":
            found.append(f"{path.name}:{node.lineno} uses float")
        elif isinstance(node, ast.Constant) and node.value == "float":
            found.append(f"{path.name}:{node.lineno} 'float' in annotation")
    return found


def test_no_float_anywhere_in_the_domain() -> None:
    files = sorted(DOMAIN_DIR.rglob("*.py"))
    assert len(files) >= 7
    offences = [hit for path in files for hit in _float_uses(path)]
    assert offences == []


def test_float_scanner_detects_floats(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("x: float = 0.5\ny = float('1')\n", encoding="utf-8")
    assert len(_float_uses(bad)) == 3


FORBIDDEN_IN_DOMAIN = (
    "fastapi",
    "sqlalchemy",
    "langgraph",
    "pydantic",
    "psycopg",
    "google",
    "anthropic",
    "openai",
)


def test_domain_imports_no_frameworks() -> None:
    for path in DOMAIN_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in FORBIDDEN_IN_DOMAIN, f"{path.name} imports {name}"
