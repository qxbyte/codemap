"""Plan 4 Task 4: Golden full-stack fixture + precision gate.

End-to-end: run ``codemap index`` on the HelloSpring fixture (Java +
MyBatis + Vue) and assert that every edge of spec §4.1's example link
chain lands at the expected confidence tier, with no surprise edges.

The fixture lives at ``tests/fixtures/scip-samples/HelloSpring/`` and
ships a Spring Boot trio (controller / service / mapper interface) + a
MyBatis Mapper XML + a Vue 2 component calling the same route. The
chain we expect to materialise:

    OrderList(Vue)
        ─calls→ route(POST /api/order/price)
                       ←routes_to─ OrderController.calcPrice
            ─calls→ OrderService.calculateOrderPrice
                ─calls→ CouponMapper.selectByUser (Java interface)
                    ─maps_to→ sql_mapping(CouponMapper#selectByUser)
                        ─accesses_table→ sf_coupon

Precision targets (ADR-0013 traded "high" for "medium" on Java
``calls`` edges; routes_to / accesses_table stay "high"):
* high tier   — every edge must be in the expected set (≥ 0.95 floor)
* medium tier — every edge must be in the expected set (≥ 0.70 floor)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codemap.cli.main import app
from codemap.core.symbol import SymbolID

runner = CliRunner()
FIXTURE = Path(__file__).parent.parent / "fixtures" / "scip-samples" / "HelloSpring"


# Edge tuples are (source-simple-name, target-simple-name-or-route-tail, kind).
# Targets that are route intermediates use the last URL segment so we don't
# tie the assertion to the synthetic SymbolID format.
EXPECTED_EDGES: set[tuple[str, str, str]] = {
    ("calcPrice", "/api/order/price", "routes_to"),  # OrderController → route
    ("calcPrice", "calculateOrderPrice", "calls"),  # Controller → Service
    ("calculateOrderPrice", "selectByUser", "calls"),  # Service → Mapper iface
    ("selectByUser", "selectByUser", "maps_to"),  # Mapper iface → sql_mapping
    ("selectByUser", "sf_coupon", "accesses_table"),  # sql_mapping → table
    ("calcPrice", "/api/order/price", "calls"),  # Vue calcPrice → route
}


def _edge_signature(edge: dict) -> tuple[str, str, str]:
    """Normalize an edge's source/target into the simple-name tuple used
    by ``EXPECTED_EDGES``. Works uniformly across all four SymbolID
    schemes — Java, MyBatis sql_mapping, scip-route, scip-table — by
    going through ``SymbolID.parse`` and taking the last descriptor's
    name. For routes the last descriptor *is* the path (e.g.
    ``/api/order/price``)."""
    return (
        _last_name(edge["source"]),
        _last_name(edge["target"]),
        edge["kind"],
    )


def _last_name(sid_str: str) -> str:
    return SymbolID.parse(sid_str).descriptors[-1].name


@pytest.fixture
def hello_spring_project(tmp_path: Path) -> Path:
    """Copy the fixture to a temp dir so the e2e run never dirties the repo."""
    dst = tmp_path / "HelloSpring"
    shutil.copytree(FIXTURE, dst)
    # Make sure no leftover index sneaks in.
    for noise in (".codemap", ".ai-memory", "target"):
        p = dst / noise
        if p.exists():
            shutil.rmtree(p)
    return dst


def _run_index(project: Path) -> list[dict]:
    result = runner.invoke(app, ["index", "--rebuild", str(project)])
    assert result.exit_code == 0, f"codemap index failed:\n{result.stdout}"
    edges_file = project / ".codemap" / "edges.json"
    assert edges_file.exists(), "edges.json not produced"
    return json.loads(edges_file.read_text())


# ---------------------------------------------------------------------------
# Chain coverage
# ---------------------------------------------------------------------------


def test_full_chain_edges_present(hello_spring_project: Path) -> None:
    edges = _run_index(hello_spring_project)
    actual = {_edge_signature(e) for e in edges}
    missing = EXPECTED_EDGES - actual
    assert not missing, (
        "chain incomplete — missing edges:\n  " + "\n  ".join(map(repr, missing))
    )


# ---------------------------------------------------------------------------
# Precision gates
# ---------------------------------------------------------------------------


def test_high_tier_precision_at_least_095(hello_spring_project: Path) -> None:
    edges = _run_index(hello_spring_project)
    high = [e for e in edges if e["confidence"] == "high"]
    assert high, "no high-confidence edges produced; fixture or pipeline broken"
    true_pos = [e for e in high if _edge_signature(e) in EXPECTED_EDGES]
    precision = len(true_pos) / len(high)
    assert precision >= 0.95, (
        f"high-tier precision {precision:.2f} < 0.95 — "
        f"surprise edges: {[_edge_signature(e) for e in high if _edge_signature(e) not in EXPECTED_EDGES]}"
    )


def test_medium_tier_precision_at_least_070(hello_spring_project: Path) -> None:
    edges = _run_index(hello_spring_project)
    medium = [e for e in edges if e["confidence"] == "medium"]
    if not medium:
        pytest.skip("no medium-confidence edges in this index")
    true_pos = [e for e in medium if _edge_signature(e) in EXPECTED_EDGES]
    precision = len(true_pos) / len(medium)
    assert precision >= 0.70, (
        f"medium-tier precision {precision:.2f} < 0.70 — "
        f"surprise edges: {[_edge_signature(e) for e in medium if _edge_signature(e) not in EXPECTED_EDGES]}"
    )
