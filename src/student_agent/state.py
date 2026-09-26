"""Internal state and handoff contracts for the L3B workflow.

These models are deliberately internal. Final outputs and observable events
still use the existing JSON schemas and :class:`TraceWriter`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .trace import TraceWriter

AgentRole = Literal[
    "coordinator",
    "entity_customer",
    "order_product",
    "shipment",
    "payment_refund",
    "policy",
    "conflict_resolver",
    "verifier",
]
TaskStatus = Literal["pending", "completed", "blocked", "failed"]
TraceEventType = Literal[
    "case_received",
    "task_assigned",
    "tool_result_consumed",
    "handoff",
    "policy_decided",
    "verification_completed",
    "case_finalized",
]


@dataclass(frozen=True)
class SpecialistTask:
    """Coordinator-owned work item sent to one specialist."""

    task_id: str
    case_id: str
    role: AgentRole
    objective: str
    allowed_tools: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)
    attempt: int = 1


@dataclass(frozen=True)
class SpecialistResult:
    """Bounded specialist handoff back to the coordinator."""

    task_id: str
    case_id: str
    role: AgentRole
    status: TaskStatus
    findings: dict[str, Any] = field(default_factory=dict)
    evidence_by_finding: dict[str, str] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    conflict_ids: tuple[str, ...] = ()
    error_code: str | None = None
    errors: dict[str, str] = field(default_factory=dict)


@dataclass
class InvestigationState:
    """Coordinator state shared across agents for one case only."""

    case_id: str
    input_case: dict[str, Any]
    resolved_order_ids: tuple[str, ...] = ()
    rejected_candidates: tuple[str, ...] = ()
    evidence_refs: set[str] = field(default_factory=set)
    specialist_results: dict[str, SpecialistResult] = field(default_factory=dict)
    conflict_ids: set[str] = field(default_factory=set)
    status: Literal[
        "received",
        "investigating",
        "ready_for_policy",
        "ready_for_verification",
        "finalized",
    ] = "received"


@dataclass(frozen=True)
class WorkflowEvent:
    """Internal event input emitted through the existing TraceWriter."""

    case_id: str
    event_type: TraceEventType
    actor: AgentRole
    target: AgentRole | None = None
    decision_code: str | None = None
    tool_name: str | None = None
    evidence_refs: tuple[str, ...] = ()
    attributes: dict[str, str | int | float | bool | None] = field(default_factory=dict)

    def emit(self, trace: TraceWriter) -> dict[str, Any]:
        return trace.emit(
            case_id=self.case_id,
            event_type=self.event_type,
            actor=self.actor,
            target=self.target,
            decision_code=self.decision_code,
            tool_name=self.tool_name,
            evidence_refs=list(self.evidence_refs) or None,
            attributes=self.attributes or None,
        )
