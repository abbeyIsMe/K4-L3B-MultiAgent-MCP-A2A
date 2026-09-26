from __future__ import annotations
 
import asyncio
import json
from pathlib import Path
 
from student_agent.config import Settings
from student_agent.contracts import Contracts
from student_agent.mcp_gateway import connect_gateway
 
 
async def main() -> None:
    root = Path(__file__).resolve().parent
    settings = Settings.load(root)
    contracts = Contracts(root / "contracts" / "schemas")
 
    async with connect_gateway(settings.mcp_endpoint, settings.team_api_key, contracts) as gateway:
        response = await gateway._session.list_tools()  # noqa: SLF001
        for tool in sorted(response.tools, key=lambda t: t.name):
            print("=" * 60)
            print(tool.name)
            print(tool.description or "(no description)")
            print(json.dumps(tool.input_schema, indent=2, ensure_ascii=False))
 
 
if __name__ == "__main__":
    asyncio.run(main())