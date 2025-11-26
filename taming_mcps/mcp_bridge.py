# THE BRIDGE: Connects generated code to active MCP sessions
from typing import Any

# This will be injected at runtime
ACTIVE_SESSIONS = {}

async def call_mcp_tool(server_name: str, tool_name: str, args: dict) -> Any:
    if server_name not in ACTIVE_SESSIONS:
        return f"Error: Server '{server_name}' is not connected."
    
    session = ACTIVE_SESSIONS[server_name]
    result = await session.call_tool(tool_name, arguments=args)
    return result.content
