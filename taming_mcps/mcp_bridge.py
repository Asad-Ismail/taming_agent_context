# THE BRIDGE: Connects generated code to active MCP sessions
from typing import Any
import json

# This will be injected at runtime
ACTIVE_SESSIONS = {}

async def call_mcp_tool(server_name: str, tool_name: str, args: dict) -> Any:
    if server_name not in ACTIVE_SESSIONS:
        return f"Error: Server '{server_name}' is not connected."
    
    session = ACTIVE_SESSIONS[server_name]
    result = await session.call_tool(tool_name, arguments=args)
    
    # Extract clean content from MCP response
    if result.content and len(result.content) > 0:
        text = result.content[0].text
        # Try to parse as JSON if it looks like JSON
        try:
            if text.strip().startswith(('{', '[')):
                return json.loads(text)
        except:
            pass
        return text
    return result.content
    