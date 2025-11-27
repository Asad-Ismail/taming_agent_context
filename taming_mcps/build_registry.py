"""
Build Registry Script - Generates Python wrappers for MCP servers.
Run this once to create the ./servers/ directory structure.
"""
import os
import asyncio
import shutil
import sqlite3
from textwrap import dedent
from typing import Any, Dict

# MCP SDK
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# --- CONFIGURATION ---
REGISTRY_ROOT = os.path.abspath("./servers")
DB_FILE = "temp_schema.db"

def generate_python_wrapper(server_name: str, tool: Dict[str, Any]) -> str:
    """
    Generates a Python file that looks like a library function but calls MCP.
    """
    name = tool['name']
    description = tool.get('description', 'No description provided.')
    schema = tool['inputSchema']
    
    # Convert JSON schema to a rough Python docstring representation
    params_doc = []
    for prop_name, prop_def in schema.get('properties', {}).items():
        p_type = prop_def.get('type', 'any')
        p_desc = prop_def.get('description', '')
        params_doc.append(f"    :param {prop_name}: ({p_type}) {p_desc}")
    
    params_str = "\n".join(params_doc) if params_doc else "    No parameters."

    # The Template: Looks like a normal function, but calls the bridge
    code = dedent(f"""\
    # WRAPPER FOR MCP TOOL: {name}
    from mcp_bridge import call_mcp_tool

    async def {name}(kwargs: dict):
        \"\"\"
        {description}

        Parameters:
    {params_str}
        \"\"\"
        return await call_mcp_tool('{server_name}', '{name}', kwargs)
    """)
    return code

async def build_code_registry():
    """Connects to real servers and generates the ./servers/ file tree."""
    print("🔨 Building Code Registry (Generating Python wrappers)...")
    
    if os.path.exists(REGISTRY_ROOT):
        shutil.rmtree(REGISTRY_ROOT)
    os.makedirs(REGISTRY_ROOT)

    # Create the bridge file that tools import to talk to sessions
    with open("mcp_bridge.py", "w") as f:
        f.write("""# THE BRIDGE: Connects generated code to active MCP sessions
            from typing import Any

            # This will be injected at runtime
            ACTIVE_SESSIONS = {}

            async def call_mcp_tool(server_name: str, tool_name: str, args: dict) -> Any:
                if server_name not in ACTIVE_SESSIONS:
                    return f"Error: Server '{server_name}' is not connected."
                
                session = ACTIVE_SESSIONS[server_name]
                result = await session.call_tool(tool_name, arguments=args)
                return result.content
            """)

    # Setup dummy DB for SQLite server
    conn = sqlite3.connect(DB_FILE)
    conn.close()

    # Definition of servers to "virtualize"
    # Using explicit versions to avoid npx cache corruption issues
    server_configs = [
        ("time", "uvx", ["mcp-server-time"]),  # uvx handles versions differently
        ("sqlite", "uvx", ["mcp-server-sqlite", "--db-path", DB_FILE]),
        ("git", "uvx", ["mcp-server-git", "--repository", os.path.dirname(os.getcwd())]),
        ("github", "npx", ["-y", "@modelcontextprotocol/server-github@2025.4.8"]),
        ("filesystem", "npx", ["-y", "@modelcontextprotocol/server-filesystem@2025.11.25", os.path.dirname(os.getcwd())]),
    ]

    for name, cmd, args in server_configs:
        # Check if command exists
        if not shutil.which(cmd):
            print(f"   Warning: Skipping '{name}': {cmd} not found")
            continue
            
        server_dir = os.path.join(REGISTRY_ROOT, name)
        os.makedirs(server_dir, exist_ok=True)
        
        # Start server to scrape tool definitions
        params = StdioServerParameters(command=cmd, args=args, env=os.environ.copy())
        
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    
                    # Generate __init__.py for imports and INDEX.md for discovery
                    init_lines = []
                    index_lines = [f"# {name.upper()} Server Tools\n"]
                    
                    for tool in tools.tools:
                        tool_def = tool.model_dump()
                        safe_name = tool_def['name']
                        description = tool_def.get('description', 'No description')
                        
                        # Write the tool wrapper file
                        wrapper_code = generate_python_wrapper(name, tool_def)
                        with open(os.path.join(server_dir, f"{safe_name}.py"), "w") as f:
                            f.write(wrapper_code)
                            
                        init_lines.append(f"from .{safe_name} import {safe_name}")
                        # INDEX only has name + description (lightweight)
                        index_lines.append(f"- **{safe_name}**: {description}")
                    
                    # Write __init__.py for imports
                    with open(os.path.join(server_dir, "__init__.py"), "w") as f:
                        f.write("\n".join(init_lines))
                    
                    # Write INDEX.md for discovery
                    with open(os.path.join(server_dir, "INDEX.md"), "w") as f:
                        f.write("\n".join(index_lines))
                        
            print(f"  Generated wrappers for '{name}' ({len(tools.tools)} tools)")
            
        except Exception as e:
            print(f"  Could not build '{name}': {e}")

    # Cleanup
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    print("Registry setup complete.\n")

async def main():
    await build_code_registry()

if __name__ == "__main__":
    asyncio.run(main())
