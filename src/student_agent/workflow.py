from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .mcp_gateway import EvidenceGateway
from .state import InvestigationState, SpecialistResult, SpecialistTask, WorkflowEvent
from .trace import TraceWriter
from .verifier import calibrate_confidence, verify_output


async def _call_for_task(
    task: SpecialistTask,
    gateway: EvidenceGateway,
    definitions: list[dict[str, Any]],
    tool_name: str,
    **arguments: str,
) -> dict[str, Any]:
    """Call one discovered tool after enforcing task and metadata contracts."""
    if tool_name not in task.allowed_tools:
        raise PermissionError(f"tool {tool_name!r} is not allowed for {task.role}")
    if task.case_id != task.context.get("case_id", task.case_id):
        raise ValueError("task context case_id mismatch")
    definition = next((item for item in definitions if item["name"] == tool_name), None)
    if definition is None:
        raise ValueError(f"tool {tool_name!r} was not returned by list_tools")
    schema = definition.get("input_schema") or {}
    supplied = {"case_id", *arguments}
    missing = set(schema.get("required", ())) - supplied
    if missing:
        raise ValueError(f"missing required arguments for {tool_name}: {sorted(missing)}")
    properties = schema.get("properties")
    if properties:
        unknown = set(arguments) - set(properties)
        if unknown:
            raise ValueError(f"unknown arguments for {tool_name}: {sorted(unknown)}")
    return await gateway.call(tool_name, case_id=task.case_id, **arguments)


def _insufficient_evidence_output(case_id: str) -> dict[str, Any]:
    return {
        "schema_version": "day09-l3b-output-v2",
        "case_id": case_id,
        "assessment": {
            "primary_issue": "insufficient_evidence",
            "secondary_issues": [],
            "case_status": "needs_investigation",
            "confidence": 0.0,
        },
        "affected_entities": {
            "order_ids": [],
            "item_ids": [],
            "seller_ids": [],
            "payment_references": [],
            "shipment_ids": [],
        },
        "entity_resolution": {
            "status": "not_found",
            "resolved_order_ids": [],
            "rejected_candidates": [],
            "confidence": 0.0,
        },
        "customer_context": {"customer_unique_id": None, "related_order_ids": []},
        "shipment_analysis": {
            "verdict": "insufficient_evidence",
            "late_seller_ids": [],
            "timeline_complete": False,
        },
        "payment_analysis": {
            "verdict": "insufficient_evidence",
            "captured_total_brl": None,
            "refunded_total_brl": None,
            "refundable_total_brl": None,
        },
        "root_cause_analysis": {"ranked_causes": [], "responsible_parties": []},
        "evidence_refs": [],
        "data_conflicts": [],
        "financial_resolution": {
            "currency": "BRL",
            "recommended_refund_brl": 0,
            "refund_lines": [],
        },
        "resolution_actions": ["provide_case_input"],
    }


async def _run_task(
    state: InvestigationState,
    task: SpecialistTask,
    calls: list[tuple[str, str, dict[str, str]]],
    definitions: list[dict[str, Any]],
    gateway: EvidenceGateway,
    trace: TraceWriter,
) -> SpecialistResult:
    WorkflowEvent(
        state.case_id,
        "task_assigned",
        actor="coordinator",
        target=task.role,
        attributes={"task_id": task.task_id},
    ).emit(trace)
    findings: dict[str, Any] = {}
    evidence_by_finding: dict[str, str] = {}
    evidence_refs: list[str] = []
    errors: dict[str, str] = {}
    status = "completed"
    for label, tool_name, arguments in calls:
        try:
            evidence = await _call_for_task(
                task, gateway, definitions, tool_name, **arguments
            )
            evidence_ref = evidence.get("evidence_ref")
            if not isinstance(evidence_ref, str):
                raise ValueError("MCP response has no evidence_ref")
            findings[label] = evidence.get("data")
            evidence_by_finding[label] = evidence_ref
            evidence_refs.append(evidence_ref)
            state.evidence_refs.add(evidence_ref)
            WorkflowEvent(
                state.case_id,
                "tool_result_consumed",
                actor=task.role,
                tool_name=tool_name,
                evidence_refs=(evidence_ref,),
            ).emit(trace)
        except Exception as exc:
            status = "blocked"
            errors[label] = type(exc).__name__
            continue
    result = SpecialistResult(
        task_id=task.task_id,
        case_id=state.case_id,
        role=task.role,
        status=status,
        findings=findings,
        evidence_by_finding=evidence_by_finding,
        evidence_refs=tuple(evidence_refs),
        error_code=next(iter(errors.values()), None),
        errors=errors,
    )
    state.specialist_results[task.task_id] = result
    handoff_attributes: dict[str, str | int | float | bool | None] = {
        "task_id": task.task_id,
        "status": status,
    }
    for index, (label, exception_class) in enumerate(errors.items()):
        arguments = next(call[2] for call in calls if call[0] == label)
        handoff_attributes.update(
            {
                f"error_{index}_label": label,
                f"error_{index}_candidate_id": arguments.get("order_id"),
                f"error_{index}_exception": exception_class,
            }
        )
    WorkflowEvent(
        state.case_id,
        "handoff",
        actor=task.role,
        target="coordinator",
        evidence_refs=tuple(evidence_refs),
        attributes=handoff_attributes,
    ).emit(trace)
    return result


def _topics(case: dict[str, Any]) -> set[str]:
    claims = case["customer_request"]["claims"]
    return {claim["topic"] for claim in claims if isinstance(claim.get("topic"), str)}


def _output_for_state(
    state: InvestigationState,
    resolution_status: str,
    resolved_order_ids: list[str],
    rejected_candidates: list[str],
    customer_unique_id: str | None = None,
    related_order_ids: list[str] | None = None,
    item_ids: list[str] | None = None,
    seller_ids: list[str] | None = None,
) -> dict[str, Any]:
    output = _insufficient_evidence_output(state.case_id)
    output["entity_resolution"] = {
        "status": resolution_status,
        "resolved_order_ids": resolved_order_ids,
        "rejected_candidates": rejected_candidates,
        "confidence": 0.0,
    }
    output["affected_entities"] = {
        "order_ids": resolved_order_ids,
        "item_ids": item_ids or [],
        "seller_ids": seller_ids or [],
        "payment_references": [],
        "shipment_ids": [],
    }
    output["customer_context"] = {
        "customer_unique_id": customer_unique_id,
        "related_order_ids": related_order_ids or [],
    }
    output["evidence_refs"] = sorted(state.evidence_refs)
    output["resolution_actions"] = ["continue_investigation"]
    return output


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _sum_payment_values(data: Any) -> Decimal | None:
    if not isinstance(data, list):
        return None
    values = [_decimal(item.get("payment_value")) for item in data if isinstance(item, dict)]
    if not values or any(value is None for value in values):
        return None
    return sum(values, Decimal("0"))


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _shipment_analysis(data: Any) -> tuple[str | None, bool, list[str]]:
    if not isinstance(data, dict):
        return None, False, []
    delivered = _parse_time(data.get("delivered_customer_at"))
    estimated = _parse_time(data.get("estimated_delivery_at"))
    limits = data.get("shipping_limits")
    events = data.get("events")
    if (
        delivered is None
        or estimated is None
        or not isinstance(limits, list)
        or not isinstance(events, list)
    ):
        return None, False, []
    seller_late = False
    late_seller_ids: list[str] = []
    carrier_events = [
        event
        for event in events
        if isinstance(event, dict) and event.get("event_type") == "carrier_handoff"
    ]
    for limit in limits:
        if not isinstance(limit, dict):
            return None, False, []
        limit_at = _parse_time(limit.get("shipping_limit_at"))
        if limit_at is None:
            return None, False, []
        carrier = carrier_events[0] if carrier_events else None
        carrier_at = _parse_time(carrier.get("event_at")) if isinstance(carrier, dict) else None
        if carrier_at is not None and carrier_at > limit_at:
            seller_late = True
            seller_id = limit.get("seller_id")
            if isinstance(seller_id, str):
                late_seller_ids.append(seller_id)
    if seller_late:
        return "seller_delay", True, sorted(set(late_seller_ids))
    if delivered > estimated:
        return "logistics_delay", True, []
    return "on_time", True, []


def _shipment_verdict(data: Any) -> str | None:
    return _shipment_analysis(data)[0]


def _decision_confidence(
    state: InvestigationState,
    policy_data: Any,
    evidence_sources: set[str],
) -> float | None:
    required = {"case_status", "recommended_action", "refund_brl", "responsible_parties"}
    if not isinstance(policy_data, dict) or not required.issubset(policy_data):
        return None
    if state.conflict_ids or len(evidence_sources) < 2:
        return None
    # ponytail: fixed conservative ceiling until confidence is calibrated on graded outcomes.
    score = Decimal("0.40")
    score += Decimal("0.20") if required.issubset(policy_data) else Decimal("0")
    score += min(Decimal("0.25"), Decimal("0.10") * len(evidence_sources))
    score += Decimal("0.15") if not state.conflict_ids else Decimal("0")
    return float(min(score, Decimal("0.85")))


def _policy_rule(policy_data: Any, issue: str) -> dict[str, Any] | None:
    if not isinstance(policy_data, dict) or not isinstance(policy_data.get("rules"), dict):
        return None
    rule = policy_data["rules"].get(issue)
    return rule if isinstance(rule, dict) else None


def _build_decision(
    state: InvestigationState,
    case: dict[str, Any],
    resolution_status: str,
    resolved_order_ids: list[str],
    rejected_candidates: list[str],
    customer_unique_id: str | None,
    related_order_ids: list[str],
    item_ids: list[str],
    seller_ids: list[str],
) -> dict[str, Any]:
    output = _output_for_state(
        state,
        resolution_status,
        resolved_order_ids,
        rejected_candidates,
        customer_unique_id,
        related_order_ids,
        item_ids,
        seller_ids,
    )
    if resolution_status != "resolved":
        return output

    results = state.specialist_results
    policy_result = results.get(f"{state.case_id}:policy")
    entity_result = results[f"{state.case_id}:entity-resolution"]
    policy_data = policy_result.findings.get("policy") if policy_result else None
    order_data = entity_result.findings.get(f"order:{resolved_order_ids[0]}")
    payment_result = results.get(f"{state.case_id}:payment-refund")
    payment_data = payment_result.findings.get("payments") if payment_result else None
    payment_total = _sum_payment_values(payment_data)
    topics = _topics(case)
    candidates: list[tuple[str, list[str]]] = []
    if (
        isinstance(order_data, dict)
        and order_data.get("order_status") == "canceled"
        and payment_total is not None
        and payment_total > 0
    ):
        candidates.append(
            ("canceled_order_paid", [f"order:{resolved_order_ids[0]}", "payments"])
        )
    if (
        isinstance(order_data, dict)
        and order_data.get("order_status") == "unavailable"
        and payment_total is not None
        and payment_total > 0
    ):
        candidates.append(
            ("unavailable_order_paid", [f"order:{resolved_order_ids[0]}", "payments"])
        )
    shipment_result = results.get(f"{state.case_id}:shipment")
    shipment_data = shipment_result.findings.get("shipment") if shipment_result else None
    shipment_verdict, shipment_complete, late_seller_ids = _shipment_analysis(shipment_data)
    if shipment_verdict == "seller_delay":
        candidates.append(("late_delivery_seller", ["shipment"]))
    elif shipment_verdict == "logistics_delay":
        candidates.append(("late_delivery_logistics", ["shipment"]))
    if "valid_split_payment" in topics and isinstance(payment_data, list) and len(payment_data) > 1:
        candidates.append(("valid_split_payment", ["payments"]))

    candidates = [candidate for candidate in candidates if candidate[0] in topics]
    if len(candidates) != 1 or policy_result is None or policy_result.status != "completed":
        return output
    issue, finding_labels = candidates[0]
    rule = _policy_rule(policy_data, issue)
    if rule is None:
        return output
    if payment_result and payment_result.errors.get("refund_timeline") and (
        "requested_full_refund" in topics or issue in {"refund_pending", "refund_failed"}
    ):
        return output
    required_fields = {"case_status", "recommended_action", "refund_brl", "responsible_parties"}
    if not required_fields.issubset(rule):
        return output
    refund = _decimal(rule["refund_brl"])
    if refund is None or refund < 0 or not isinstance(rule["recommended_action"], str):
        return output
    parties = rule["responsible_parties"]
    if not isinstance(parties, list) or not all(
        isinstance(item, dict) and isinstance(item.get("party_type"), str)
        and (isinstance(item.get("party_id"), str) or item.get("party_id") is None)
        for item in parties
    ):
        return output
    refs = [policy_result.evidence_by_finding["policy"]]
    refs.extend(
        entity_result.evidence_by_finding[label]
        for label in finding_labels
        if label in entity_result.evidence_by_finding
    )
    if payment_result and "payments" in finding_labels:
        refs.append(payment_result.evidence_by_finding["payments"])
    if shipment_result and "shipment" in finding_labels:
        refs.append(shipment_result.evidence_by_finding["shipment"])
    confidence = _decision_confidence(
        state,
        rule,
        {"policy", "order", *finding_labels},
    )
    if confidence is None:
        return output
    output["assessment"] = {
        "primary_issue": issue,
        "secondary_issues": [],
        "case_status": rule["case_status"],
        "confidence": confidence,
    }
    output["root_cause_analysis"] = {
        "ranked_causes": [{"cause_code": issue.upper(), "rank": 1}],
        "responsible_parties": parties,
    }
    output["financial_resolution"] = {
        "currency": "BRL",
        "recommended_refund_brl": float(refund),
        "refund_lines": (
            [
                {
                    "reason_code": issue,
                    "amount_brl": float(refund),
                    "entity_id": resolved_order_ids[0],
                }
            ]
            if refund > 0
            else []
        ),
    }
    output["resolution_actions"] = [rule["recommended_action"]]
    output["evidence_refs"] = sorted(set(output["evidence_refs"]) | set(refs))
    output["claim_assessments"] = [
        {
            "claim_id": claim["claim_id"],
            "verdict": "supported" if claim["topic"] == issue else "insufficient_evidence",
            "confidence": confidence if claim["topic"] == issue else 0.0,
            "evidence_refs": (
                refs if claim["topic"] == issue else []
            ),
        }
        for claim in case["customer_request"]["claims"]
    ]
    if payment_total is not None:
        payment_verdict = {
            "canceled_order_paid": "capture_mismatch",
            "unavailable_order_paid": "capture_mismatch",
            "valid_split_payment": "reconciled",
        }.get(issue, "insufficient_evidence")
        output["payment_analysis"] = {
            "verdict": payment_verdict,
            "captured_total_brl": float(payment_total),
            "refunded_total_brl": None,
            "refundable_total_brl": float(refund) if issue == "valid_split_payment" else None,
        }
    if shipment_verdict is not None:
        output["shipment_analysis"]["verdict"] = shipment_verdict
        output["shipment_analysis"]["timeline_complete"] = shipment_complete
        output["shipment_analysis"]["late_seller_ids"] = late_seller_ids
    return output


async def solve_case(
    case: dict[str, Any], gateway: EvidenceGateway, trace: TraceWriter
) -> dict[str, Any]:
    """Run the safe Pha 3 boundary until official case fields are available.

    Entity resolution and specialist calls remain blocked when the input does
    not provide a resolved order. This prevents guessed arguments and audit
    calls against an unknown case shape.
    """
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("case must contain a non-empty case_id")

    state = InvestigationState(case_id=case_id, input_case=case, status="investigating")
    try:
        definitions = await gateway.list_tool_definitions()
    except Exception:
        definitions = []

    required_case_fields = {"customer_request", "candidate_order_ids", "investigation_scope"}
    if not required_case_fields.issubset(case):
        task = SpecialistTask(
            task_id=f"{case_id}:entity-resolution",
            case_id=case_id,
            role="entity_customer",
            objective="resolve an order candidate from MCP evidence",
            context={"case_id": case_id},
        )
        WorkflowEvent(
            case_id,
            "task_assigned",
            actor="coordinator",
            target=task.role,
            attributes={"task_id": task.task_id},
        ).emit(trace)
        result = SpecialistResult(
            task_id=task.task_id,
            case_id=case_id,
            role=task.role,
            status="blocked",
            error_code="missing_case_input",
        )
        state.specialist_results[task.task_id] = result
        WorkflowEvent(
            case_id,
            "handoff",
            actor=task.role,
            target="coordinator",
            attributes={"task_id": task.task_id, "status": result.status},
        ).emit(trace)
        output = calibrate_confidence(_insufficient_evidence_output(case_id), state)
        verify_output(output, trace.contracts, state)
        state.status = "ready_for_verification"
        WorkflowEvent(
            case_id,
            "verification_completed",
            actor="verifier",
            decision_code="blocked_missing_case_input",
        ).emit(trace)
        return output

    customer_hint = case.get("customer_unique_id_hint")
    claimed_order_id = case["customer_request"].get("claimed_order_id")
    candidate_order_ids = case.get("candidate_order_ids", [])
    order_ids = list(dict.fromkeys([*candidate_order_ids, claimed_order_id]))
    task = SpecialistTask(
        task_id=f"{case_id}:entity-resolution",
        case_id=case_id,
        role="entity_customer",
        objective="resolve an order candidate from MCP evidence",
        allowed_tools=("get_customer_history", "get_order"),
        context={"case_id": case_id},
    )
    calls: list[tuple[str, str, dict[str, str]]] = []
    if case["investigation_scope"].get("include_customer_history") and isinstance(
        customer_hint, str
    ):
        calls.append(
            ("customer_history", "get_customer_history", {"customer_unique_id": customer_hint})
        )
    calls.extend(
        (f"order:{order_id}", "get_order", {"order_id": order_id}) for order_id in order_ids
    )
    entity_result = await _run_task(state, task, calls, definitions, gateway, trace)

    customer_unique_id = None
    related_order_ids: list[str] = []
    customer_data = entity_result.findings.get("customer_history")
    history_order_ids: set[str] = set()
    if isinstance(customer_data, dict):
        if isinstance(customer_data.get("customer_unique_id"), str):
            customer_unique_id = customer_data["customer_unique_id"]
        orders = customer_data.get("orders")
        if isinstance(orders, list):
            history_order_ids = {
                item["order_id"]
                for item in orders
                if isinstance(item, dict) and isinstance(item.get("order_id"), str)
            }
            related_order_ids = sorted(history_order_ids)

    supported: list[str] = []
    rejected: list[str] = []
    missing: list[str] = []
    for order_id in order_ids:
        data = entity_result.findings.get(f"order:{order_id}")
        if isinstance(data, dict) and data.get("order_id") == order_id:
            supported.append(order_id)
        elif isinstance(data, dict) and isinstance(data.get("order_id"), str):
            rejected.append(order_id)
        else:
            missing.append(order_id)

    history_attempted = any(label == "customer_history" for label, _, _ in calls)
    history_available = isinstance(customer_data, dict) and isinstance(
        customer_data.get("orders"), list
    )
    history_matches = set(supported) & history_order_ids
    if (
        (
            len(supported) == 1
            and not rejected
            and history_attempted
            and history_available
            and history_matches == set(supported)
            and missing
        )
        or (not missing and len(supported) == 1 and not history_attempted)
    ):
        resolution_status = "resolved"
        resolved_order_ids = supported
    elif not missing and not supported:
        resolution_status = "not_found"
        resolved_order_ids = []
    else:
        resolution_status = "ambiguous"
        resolved_order_ids = []

    item_ids: list[str] = []
    seller_ids: list[str] = []
    if resolution_status == "resolved":
        order_id = resolved_order_ids[0]
        topics = _topics(case)
        policy_task = SpecialistTask(
            task_id=f"{case_id}:policy",
            case_id=case_id,
            role="policy",
            objective="retrieve the policy evidence for this case",
            allowed_tools=("get_policy",),
            context={"case_id": case_id},
        )
        await _run_task(
            state,
            policy_task,
            [("policy", "get_policy", {"policy_version": case["policy_version"]})],
            definitions,
            gateway,
            trace,
        )
        if case["investigation_scope"].get("include_product_context"):
            product_task = SpecialistTask(
                task_id=f"{case_id}:order-product",
                case_id=case_id,
                role="order_product",
                objective="collect order, item, product and seller evidence",
                allowed_tools=("get_order_items", "get_product_context", "get_sellers"),
                context={"case_id": case_id},
            )
            product_result = await _run_task(
                state,
                product_task,
                [
                    ("items", "get_order_items", {"order_id": order_id}),
                    ("products", "get_product_context", {"order_id": order_id}),
                    ("sellers", "get_sellers", {"order_id": order_id}),
                ],
                definitions,
                gateway,
                trace,
            )
            items = product_result.findings.get("items", [])
            if isinstance(items, list):
                item_ids = [
                    item["order_item_id"]
                    for item in items
                    if isinstance(item, dict) and isinstance(item.get("order_item_id"), str)
                ]
                seller_ids = [
                    item["seller_id"]
                    for item in items
                    if isinstance(item, dict) and isinstance(item.get("seller_id"), str)
                ]
        if topics & {"late_delivery_seller", "late_delivery_logistics"}:
            shipment_task = SpecialistTask(
                task_id=f"{case_id}:shipment",
                case_id=case_id,
                role="shipment",
                objective="collect shipment evidence for the claimed delivery issue",
                allowed_tools=("get_shipment_summary",),
                context={"case_id": case_id},
            )
            await _run_task(
                state,
                shipment_task,
                [("shipment", "get_shipment_summary", {"order_id": order_id})],
                definitions,
                gateway,
                trace,
            )
        if topics & {
            "valid_split_payment",
            "payment_mismatch",
            "duplicate_charge",
            "refund_pending",
            "refund_failed",
            "requested_full_refund",
            "canceled_order_paid",
            "unavailable_order_paid",
        }:
            payment_task = SpecialistTask(
                task_id=f"{case_id}:payment-refund",
                case_id=case_id,
                role="payment_refund",
                objective="collect payment and refund evidence for the claims",
                allowed_tools=("get_order_payments", "get_payment_timeline", "get_refund_timeline"),
                context={"case_id": case_id},
            )
            payment_calls = [
                ("payments", "get_order_payments", {"order_id": order_id}),
                ("payment_timeline", "get_payment_timeline", {"order_id": order_id}),
            ]
            if topics & {"refund_pending", "refund_failed", "requested_full_refund"}:
                payment_calls.append(
                    ("refund_timeline", "get_refund_timeline", {"order_id": order_id})
                )
            await _run_task(state, payment_task, payment_calls, definitions, gateway, trace)

    output = _build_decision(
        state,
        case,
        resolution_status,
        resolved_order_ids,
        rejected,
        customer_unique_id,
        related_order_ids,
        item_ids,
        seller_ids,
    )
    state.status = "ready_for_verification"
    output = calibrate_confidence(output, state)
    verify_output(output, trace.contracts, state)
    state.status = "finalized"
    decision_made = output["assessment"]["primary_issue"] != "insufficient_evidence"
    if decision_made:
        WorkflowEvent(
            case_id,
            "policy_decided",
            actor="policy",
            decision_code=output["assessment"]["primary_issue"],
            evidence_refs=tuple(output["evidence_refs"]),
        ).emit(trace)
    WorkflowEvent(
        case_id,
        "verification_completed",
        actor="verifier",
        decision_code="business_decision_verified" if decision_made else "needs_investigation",
    ).emit(trace)
    return output
