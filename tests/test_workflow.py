from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from student_agent.contracts import Contracts
from student_agent.mcp_gateway import EvidenceGateway
from student_agent.state import InvestigationState, SpecialistTask
from student_agent.trace import TraceWriter
from student_agent.verifier import VerificationError, verify_output
from student_agent.workflow import _call_for_task, _insufficient_evidence_output, solve_case


class FakeGateway:
    def __init__(
        self,
        *,
        ambiguous: bool = False,
        fail_tool: str | None = None,
        fail_order_id: str | None = None,
        order_status: str = "delivered",
        policy_rules: dict | None = None,
        shipment_data: dict | None = None,
        customer_history_orders: list[dict] | None = None,
    ) -> None:
        self.calls: list[tuple[str, str, dict[str, str]]] = []
        self.ambiguous = ambiguous
        self.fail_tool = fail_tool
        self.fail_order_id = fail_order_id
        self.order_status = order_status
        self.policy_rules = policy_rules or {}
        self.shipment_data = shipment_data
        self.customer_history_orders = customer_history_orders or [{"order_id": "ord-good"}]

    async def list_tool_definitions(self) -> list[dict]:
        required = {
            "get_customer_history": ["case_id", "customer_unique_id"],
            "get_order": ["case_id", "order_id"],
            "get_order_items": ["case_id", "order_id"],
            "get_order_payments": ["case_id", "order_id"],
            "get_payment_timeline": ["case_id", "order_id"],
            "get_policy": ["case_id", "policy_version"],
            "get_product_context": ["case_id", "order_id"],
            "get_refund_timeline": ["case_id", "order_id"],
            "get_sellers": ["case_id", "order_id"],
            "get_shipment_summary": ["case_id", "order_id"],
        }
        return [
            {
                "name": name,
                "description": "fake",
                "input_schema": {
                    "type": "object",
                    "required": args,
                    "properties": {argument: {"type": "string"} for argument in args},
                },
            }
            for name, args in required.items()
        ]

    async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict:
        self.calls.append((tool_name, case_id, arguments))
        order_id = arguments.get("order_id", "ord-good")
        if self.fail_tool == tool_name or (
            tool_name == "get_order" and order_id == self.fail_order_id
        ):
            raise RuntimeError("fake MCP failure")
        if tool_name == "get_order":
            returned_id = order_id if self.ambiguous or order_id == "ord-good" else "ord-other"
            data = {
                "order_id": returned_id,
                "customer_id": "cust-1",
                "order_status": self.order_status,
            }
        elif tool_name == "get_customer_history":
            data = {
                "customer_unique_id": arguments["customer_unique_id"],
                "orders": self.customer_history_orders,
            }
        elif tool_name == "get_order_items":
            data = [
                {
                    "order_id": order_id,
                    "order_item_id": "item-1",
                    "product_id": "prod-1",
                    "seller_id": "seller-1",
                }
            ]
        elif tool_name == "get_product_context":
            data = [
                {
                    "order_item_id": "item-1",
                    "product_id": "prod-1",
                    "seller_id": "seller-1",
                    "product": {"product_id": "prod-1"},
                }
            ]
        elif tool_name == "get_sellers":
            data = [{"seller_id": "seller-1"}]
        elif tool_name == "get_shipment_summary":
            data = self.shipment_data or {
                "order_id": order_id,
                "events": [],
                "shipping_limits": [],
            }
        elif tool_name == "get_order_payments":
            data = [{"order_id": order_id, "payment_value": "10"}]
        elif tool_name == "get_payment_timeline":
            data = {"order_id": order_id, "payments": [], "events": []}
        elif tool_name == "get_policy":
            data = {
                "policy_version": arguments["policy_version"],
                "rules": self.policy_rules,
            }
        else:
            data = {"order_id": order_id, "events": []}
        suffix = len(self.calls) + 20
        return {
            "schema_version": "day09-mcp-evidence-v1",
            "evidence_ref": f"ev_{tool_name}_{suffix:020d}",
            "result_hash": "sha256:" + "0" * 64,
            "domain": "order",
            "data": data,
        }


def test_missing_case_fields_blocks_without_mcp_call(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace = TraceWriter(tmp_path / "trace.jsonl", contracts)
    gateway = FakeGateway()

    case_id = "L3B_CASE_001"
    trace.emit(case_id=case_id, event_type="case_received", actor="coordinator")
    output = asyncio.run(solve_case({"case_id": case_id}, gateway, trace))
    trace.emit(case_id=case_id, event_type="case_finalized", actor="coordinator")

    contracts.validate_output(output, "workflow output")
    assert output["assessment"]["case_status"] == "needs_investigation"
    assert gateway.calls == []
    events = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert [event["event_type"] for event in events] == [
        "case_received",
        "task_assigned",
        "handoff",
        "verification_completed",
        "case_finalized",
    ]
    assert {event["case_id"] for event in events} == {case_id}


def _case() -> dict:
    return {
        "case_id": "L3B_CASE_001",
        "policy_version": "day09-business-v1",
        "customer_unique_id_hint": "cust-1",
        "customer_request": {
            "claimed_order_id": "ord-bad",
            "claims": [
                {"claim_id": "claim-1", "topic": "payment_mismatch"},
                {"claim_id": "claim-2", "topic": "late_delivery_seller"},
            ],
        },
        "candidate_order_ids": ["ord-good", "ord-bad"],
        "investigation_scope": {
            "include_customer_history": True,
            "include_product_context": True,
            "require_independent_verification": True,
        },
    }


def test_resolves_candidate_and_links_evidence_to_case(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace = TraceWriter(tmp_path / "trace.jsonl", contracts)
    gateway = FakeGateway(
        fail_order_id="ord-bad",
        customer_history_orders=[{"order_id": "ord-good"}],
    )

    output = asyncio.run(solve_case(_case(), gateway, trace))

    assert output["entity_resolution"]["status"] == "resolved"
    assert output["entity_resolution"]["resolved_order_ids"] == ["ord-good"]
    assert output["entity_resolution"]["rejected_candidates"] == []
    assert output["evidence_refs"]
    assert {case_id for _, case_id, _ in gateway.calls} == {"L3B_CASE_001"}
    events = [json.loads(line) for line in trace.path.read_text().splitlines()]
    consumed = [event for event in events if event["event_type"] == "tool_result_consumed"]
    assert consumed
    assert all(event["case_id"] == "L3B_CASE_001" for event in consumed)
    assert all(event["evidence_refs"] for event in consumed)


def test_customer_history_related_orders_are_unique_and_schema_valid(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace = TraceWriter(tmp_path / "trace.jsonl", contracts)
    gateway = FakeGateway(
        customer_history_orders=[
            {"order_id": "ord-related"},
            {"order_id": "ord-related"},
        ]
    )

    output = asyncio.run(solve_case(_case(), gateway, trace))

    contracts.validate_output(output, "workflow output")
    assert output["customer_context"]["related_order_ids"] == ["ord-related"]


def test_tool_permission_is_checked_before_gateway_call() -> None:
    gateway = FakeGateway()
    task = SpecialistTask(
        task_id="task-1",
        case_id="L3B_CASE_001",
        role="shipment",
        objective="shipment",
        allowed_tools=("get_shipment_summary",),
    )
    definitions = asyncio.run(gateway.list_tool_definitions())

    with pytest.raises(PermissionError):
        asyncio.run(_call_for_task(task, gateway, definitions, "get_order", order_id="ord-good"))
    assert gateway.calls == []


def test_ambiguous_resolution_stops_dependent_specialists(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace = TraceWriter(tmp_path / "trace.jsonl", contracts)
    gateway = FakeGateway(ambiguous=True)

    output = asyncio.run(solve_case(_case(), gateway, trace))

    assert output["entity_resolution"]["status"] == "ambiguous"
    assert output["assessment"]["case_status"] == "needs_investigation"
    assert "get_order_items" not in [tool for tool, _, _ in gateway.calls]


def test_mcp_error_does_not_retry_or_run_dependents(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace = TraceWriter(tmp_path / "trace.jsonl", contracts)
    gateway = FakeGateway(fail_tool="get_order")

    output = asyncio.run(solve_case(_case(), gateway, trace))

    assert output["assessment"]["case_status"] == "needs_investigation"
    assert [tool for tool, _, _ in gateway.calls].count("get_order") == 2
    assert "get_policy" not in [tool for tool, _, _ in gateway.calls]


def test_customer_history_error_does_not_block_order_resolution(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace = TraceWriter(tmp_path / "trace.jsonl", contracts)
    gateway = FakeGateway(fail_tool="get_customer_history")

    output = asyncio.run(solve_case(_case(), gateway, trace))

    assert output["entity_resolution"]["status"] == "ambiguous"
    assert [tool for tool, _, _ in gateway.calls].count("get_order") == 2


def test_one_order_error_still_checks_other_candidates(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace = TraceWriter(tmp_path / "trace.jsonl", contracts)
    gateway = FakeGateway(
        fail_order_id="ord-bad",
        customer_history_orders=[{"order_id": "ord-good"}, {"order_id": "ord-good"}],
    )

    output = asyncio.run(solve_case(_case(), gateway, trace))

    assert output["entity_resolution"]["status"] == "resolved"
    assert output["entity_resolution"]["resolved_order_ids"] == ["ord-good"]
    assert output["entity_resolution"]["rejected_candidates"] == []
    assert [
        arguments.get("order_id")
        for tool, _, arguments in gateway.calls
        if tool == "get_order"
    ] == ["ord-good", "ord-bad"]
    events = [json.loads(line) for line in trace.path.read_text().splitlines()]
    handoff = next(
        event
        for event in events
        if event["event_type"] == "handoff"
        and event["attributes"].get("task_id") == "L3B_CASE_001:entity-resolution"
    )
    assert handoff["attributes"]["error_0_label"] == "order:ord-bad"
    assert handoff["attributes"]["error_0_candidate_id"] == "ord-bad"
    assert handoff["attributes"]["error_0_exception"] == "RuntimeError"
    assert [tool for tool, _, _ in gateway.calls].count("get_order") == 2


def test_refund_error_keeps_payment_evidence_without_refund_conclusion(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace = TraceWriter(tmp_path / "trace.jsonl", contracts)
    gateway = FakeGateway(fail_tool="get_refund_timeline", fail_order_id="ord-bad")
    case = _case()
    case["customer_request"]["claims"].append(
        {"claim_id": "claim-3", "topic": "requested_full_refund"}
    )

    output = asyncio.run(solve_case(case, gateway, trace))

    assert output["evidence_refs"]
    assert output["payment_analysis"]["verdict"] == "insufficient_evidence"
    assert output["financial_resolution"]["recommended_refund_brl"] == 0
    assert [tool for tool, _, _ in gateway.calls][-1] == "get_refund_timeline"


def test_policy_maps_supported_issue_and_emits_policy_decision(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace = TraceWriter(tmp_path / "trace.jsonl", contracts)
    gateway = FakeGateway(
        fail_order_id="ord-bad",
        order_status="canceled",
        policy_rules={
            "canceled_order_paid": {
                "case_status": "action_required",
                "recommended_action": "issue_refund",
                "refund_brl": 10.0,
                "responsible_parties": [{"party_type": "platform", "party_id": None}],
            }
        },
    )
    case = _case()
    case["customer_request"]["claims"] = [
        {"claim_id": "claim-1", "topic": "canceled_order_paid"}
    ]

    output = asyncio.run(solve_case(case, gateway, trace))

    assert output["assessment"]["primary_issue"] == "canceled_order_paid"
    assert output["assessment"]["confidence"] == 0.85
    assert output["financial_resolution"]["recommended_refund_brl"] == 10.0
    assert output["payment_analysis"]["verdict"] == "capture_mismatch"
    assert (
        sum(line["amount_brl"] for line in output["financial_resolution"]["refund_lines"])
        == 10.0
    )
    events = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert [event["event_type"] for event in events].count("policy_decided") == 1
    assert all(event["case_id"] == case["case_id"] for event in events)


def test_unavailable_paid_maps_payment_capture_mismatch(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace = TraceWriter(tmp_path / "trace.jsonl", contracts)
    gateway = FakeGateway(
        fail_order_id="ord-bad",
        order_status="unavailable",
        policy_rules={
            "unavailable_order_paid": {
                "case_status": "action_required",
                "recommended_action": "issue_refund",
                "refund_brl": 10.0,
                "responsible_parties": [{"party_type": "platform", "party_id": None}],
            }
        },
    )
    case = _case()
    case["customer_request"]["claims"] = [
        {"claim_id": "claim-1", "topic": "unavailable_order_paid"}
    ]

    output = asyncio.run(solve_case(case, gateway, trace))

    assert output["assessment"]["primary_issue"] == "unavailable_order_paid"
    assert output["payment_analysis"]["verdict"] == "capture_mismatch"


def test_shipment_decision_links_shipment_ref_and_completes_timeline(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace = TraceWriter(tmp_path / "trace.jsonl", contracts)
    gateway = FakeGateway(
        fail_order_id="ord-bad",
        policy_rules={
            "late_delivery_logistics": {
                "case_status": "action_required",
                "recommended_action": "review_delivery",
                "refund_brl": 0.0,
                "responsible_parties": [
                    {"party_type": "logistics_provider", "party_id": None}
                ],
            }
        },
        shipment_data={
            "order_id": "ord-good",
            "delivered_customer_at": "2025-01-03T00:00:00+00:00",
            "estimated_delivery_at": "2025-01-02T00:00:00+00:00",
            "events": [],
            "shipping_limits": [],
        },
    )
    case = _case()
    case["customer_request"]["claims"] = [
        {"claim_id": "claim-1", "topic": "late_delivery_logistics"}
    ]

    output = asyncio.run(solve_case(case, gateway, trace))

    shipment_ref = next(
        ref for tool, _, _ in gateway.calls
        if tool == "get_shipment_summary"
        for ref in output["evidence_refs"]
        if ref.startswith("ev_get_shipment_summary_")
    )
    assert output["assessment"]["primary_issue"] == "late_delivery_logistics"
    assert output["shipment_analysis"]["timeline_complete"] is True
    assert shipment_ref in output["claim_assessments"][0]["evidence_refs"]
    assert output["root_cause_analysis"]["ranked_causes"] == [
        {"cause_code": "LATE_DELIVERY_LOGISTICS", "rank": 1}
    ]


def test_shipment_claim_without_complete_timeline_is_not_supported(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace = TraceWriter(tmp_path / "trace.jsonl", contracts)
    gateway = FakeGateway(
        policy_rules={
            "late_delivery_logistics": {
                "case_status": "action_required",
                "recommended_action": "review_delivery",
                "refund_brl": 0.0,
                "responsible_parties": [
                    {"party_type": "logistics_provider", "party_id": None}
                ],
            }
        },
        shipment_data={"order_id": "ord-good", "events": [], "shipping_limits": []},
    )
    case = _case()
    case["customer_request"]["claims"] = [
        {"claim_id": "claim-1", "topic": "late_delivery_logistics"}
    ]

    output = asyncio.run(solve_case(case, gateway, trace))

    assert output["assessment"]["case_status"] == "needs_investigation"
    assert "claim_assessments" not in output


def test_gateway_caches_tool_definitions_for_gateway_lifetime() -> None:
    class Session:
        calls = 0

        async def list_tools(self) -> SimpleNamespace:
            self.calls += 1
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(
                        name="get_order",
                        description="order",
                        inputSchema={"type": "object", "required": ["case_id"]},
                    )
                ]
            )

    root = Path(__file__).resolve().parents[1]
    session = Session()
    gateway = EvidenceGateway(session, Contracts(root / "contracts" / "schemas"))

    first = asyncio.run(gateway.list_tool_definitions())
    second = asyncio.run(gateway.list_tool_definitions())

    assert first == second
    assert session.calls == 1


def test_unsupported_claim_stays_needs_investigation(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    trace = TraceWriter(tmp_path / "trace.jsonl", contracts)
    case = _case()
    case["customer_request"]["claims"] = [
        {"claim_id": "claim-1", "topic": "unsupported_claim"}
    ]

    output = asyncio.run(solve_case(case, FakeGateway(), trace))

    assert output["assessment"]["primary_issue"] == "insufficient_evidence"
    assert output["assessment"]["case_status"] == "needs_investigation"


def test_verifier_rejects_conflict_and_state_provenance_mismatch() -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    output = _insufficient_evidence_output("L3B_CASE_001")
    output["assessment"]["primary_issue"] = "canceled_order_paid"
    output["assessment"]["case_status"] = "action_required"
    output["evidence_refs"] = ["ev_test_00000000000000000000"]
    output["data_conflicts"] = [
        {
            "field": "order_status",
            "sources": ["order", "history"],
            "selected_source": None,
            "resolution_code": "unresolved",
        }
    ]

    with pytest.raises(VerificationError):
        verify_output(output, contracts)

    output["data_conflicts"] = []
    state = InvestigationState(
        case_id="L3B_CASE_001", input_case={}, evidence_refs=set()
    )
    with pytest.raises(VerificationError):
        verify_output(output, contracts, state)


def test_verifier_accepts_safe_fallback_without_evidence() -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")

    output = _insufficient_evidence_output("L3B_CASE_001")

    assert verify_output(output, contracts) == output


def test_verifier_rejects_schema_error() -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    output = _insufficient_evidence_output("L3B_CASE_001")
    del output["assessment"]["confidence"]

    with pytest.raises(ValueError):
        verify_output(output, contracts)


def test_verifier_rejects_status_refund_conflict() -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = Contracts(root / "contracts" / "schemas")
    output = _insufficient_evidence_output("L3B_CASE_001")
    output["assessment"] = {
        "primary_issue": "insufficient_evidence",
        "secondary_issues": [],
        "case_status": "no_action",
        "confidence": 0.0,
    }

    with pytest.raises(VerificationError):
        verify_output(output, contracts)
