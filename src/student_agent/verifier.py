"""Deterministic Pha 4 checks for an already-built L3B output."""

from __future__ import annotations

import math
from typing import Any

from .contracts import Contracts
from .state import InvestigationState


class VerificationError(ValueError):
    """Raised when a schema-valid output violates a known invariant."""


def calibrate_confidence(
    output: dict[str, Any], state: InvestigationState | None = None
) -> dict[str, Any]:
    """Keep the conservative fallback when there is no evidence signal."""
    if (
        output["assessment"]["case_status"] == "needs_investigation"
        and not output["evidence_refs"]
        and (state is None or not state.evidence_refs)
    ):
        output["assessment"]["confidence"] = 0.0
    return output


def verify_output(
    output: dict[str, Any],
    contracts: Contracts,
    state: InvestigationState | None = None,
) -> dict[str, Any]:
    """Validate public schema, then enforce only deterministic cross-field rules."""
    contracts.validate_output(output, "workflow output")

    assessment = output["assessment"]
    status = assessment["case_status"]
    primary_issue = assessment["primary_issue"]
    confidence = assessment["confidence"]
    evidence_refs = set(output["evidence_refs"])
    financial = output["financial_resolution"]
    refund = financial["recommended_refund_brl"]
    line_total = sum(line["amount_brl"] for line in financial["refund_lines"])

    if not 0 <= confidence <= 1:
        raise VerificationError("assessment.confidence must be in [0, 1]")
    if primary_issue == "insufficient_evidence" and status != "needs_investigation":
        raise VerificationError("insufficient_evidence requires needs_investigation")
    if not evidence_refs and status != "needs_investigation":
        raise VerificationError("missing evidence requires needs_investigation")
    if status == "no_action" and (refund != 0 or financial["refund_lines"]):
        raise VerificationError("no_action cannot recommend a refund")
    if not math.isclose(refund, line_total, abs_tol=0.01):
        raise VerificationError("recommended_refund_brl must equal refund_lines total")
    unresolved_conflict = any(
        conflict["selected_source"] is None for conflict in output["data_conflicts"]
    )
    if unresolved_conflict and status != "needs_investigation":
        raise VerificationError("unresolved conflicts require needs_investigation")
    if state is not None:
        if output["case_id"] != state.case_id:
            raise VerificationError("output case_id does not match investigation state")
        if not evidence_refs.issubset(state.evidence_refs):
            raise VerificationError("output contains evidence outside investigation state")

    return output
