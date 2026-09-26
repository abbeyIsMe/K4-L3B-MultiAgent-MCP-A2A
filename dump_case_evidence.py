"""Chạy 1 lần để in ra input schema thật của từng MCP tool.

Cách chạy (từ root repo, venv đã active):
    python dump_tool_schemas.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from student_agent.cases import load_case_set
from student_agent.config import Settings
from student_agent.contracts import Contracts
from student_agent.mcp_gateway import connect_gateway

CASE_ID = "L3B_CASE_001"


async def main() -> None:
    root = Path(__file__).resolve().parent
    settings = Settings.load(root)
    contracts = Contracts(root / "contracts" / "schemas")
    case_set = load_case_set(root)
    case = case_set.cases[CASE_ID]
    print("--- case input ---")
    print(json.dumps(case, indent=2, ensure_ascii=False))

    customer_request = case.get("customer_request", {}) or {}
    order_id = customer_request.get("claimed_order_id") or case["candidate_order_ids"][0]
    customer_unique_id = case.get("customer_unique_id_hint")
    policy_version = case.get("policy_version")

    async with connect_gateway(settings.mcp_endpoint, settings.team_api_key, contracts) as gateway:
        calls = [
            ("get_order", {"order_id": order_id}),
            ("get_order_items", {"order_id": order_id}),
            ("get_order_payments", {"order_id": order_id}),
            ("get_payment_timeline", {"order_id": order_id}),
            ("get_refund_timeline", {"order_id": order_id}),
            ("get_shipment_summary", {"order_id": order_id}),
            ("get_sellers", {"order_id": order_id}),
            ("get_product_context", {"order_id": order_id}),
        ]
        if customer_unique_id:
            calls.append(("get_customer_history", {"customer_unique_id": customer_unique_id}))
        if policy_version:
            calls.append(("get_policy", {"policy_version": policy_version}))

        for tool_name, args in calls:
            print("=" * 60)
            print(tool_name, args)
            try:
                raw = await gateway._session.call_tool(  # noqa: SLF001
                    tool_name, arguments={"case_id": CASE_ID, **args}
                )
                print("is_error:", getattr(raw, "is_error", getattr(raw, "isError", None)))
                for block in raw.content:
                    print("content block:", repr(block))
                structured = getattr(raw, "structuredContent", None) or getattr(
                    raw, "structured_content", None
                )
                print("structuredContent:", structured)
            except Exception as exc:  # noqa: BLE001
                print(f"TRANSPORT ERROR: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())



if __name__ == "__main__":
    asyncio.run(main())