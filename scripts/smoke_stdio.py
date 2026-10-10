"""Echte stdio-smoke-test: start de server als subprocess en spreek hem aan
via een MCP-client. Bewijst dat initialisatie + tool-calls end-to-end werken.
Dit script is een dev-help (niet onderdeel van pytest)."""

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from anwb_files_mcp import __version__


async def main() -> None:
    params = StdioServerParameters(command="anwb-files-mcp", args=[])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            print(f"server: {info.serverInfo.name}")
            tools = await session.list_tools()
            print("tools:", [t.name for t in tools.tools])

            # Totals (goedkoop, landelijk).
            res = await session.call_tool("get_totals", {})
            print("\nget_totals ->", res.content[0].text[:400])

            # Top-2 files landelijk (garantie op inhoud, onafhankelijk van de dag).
            res = await session.call_tool("get_files", {"max_results": 2})
            print("\nget_files(top2) ->", res.content[0].text[:700])

            # Categorie roadworks.
            res = await session.call_tool("get_incidents", {"category": "roadworks", "max_results": 1})
            print("\nget_incidents(roadworks) ->", res.content[0].text[:400])


if __name__ == "__main__":
    anyio.run(main)
