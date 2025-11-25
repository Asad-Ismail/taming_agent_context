import os
import json
import asyncio
import shutil
import sqlite3
from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# --- CONFIGURATION ---
REGISTRY_ROOT = os.path.abspath("./servers")
DB_FILE = "temp_schema.db"
# Use parent directory as Git repo (current folder might be a subdirectory)
GIT_REPO = os.path.abspath(os.path.join(os.getcwd(), ".."))

# --- PHASE 1: BUILD THE REGISTRY FROM LIVE SERVERS ---

async def fetch_and_save_server_tools(server_name, command, args, env=None):
    """
    Boots a REAL MCP server, asks for its tools, and saves them 
    into the blog's specific folder structure: ./servers/{name}/{tool}.json
    """
    server_dir = os.path.join(REGISTRY_ROOT, server_name)
    if os.path.exists(server_dir):
        shutil.rmtree(server_dir)
    os.makedirs(server_dir)
    
    print(f"📥 Connecting to live '{server_name}' server via uvx...")
    
    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=env or os.environ.copy()
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # GET REAL TOOLS
                tools_list = await session.list_tools()
                tool_names = []
                
                print(f"   Found {len(tools_list.tools)} tools. Saving to disk...")
                
                for tool in tools_list.tools:
                    t_def = tool.model_dump()
                    safe_name = t_def['name']
                    
                    # Save individual tool definition: servers/{server}/{tool}.json
                    with open(os.path.join(server_dir, f"{safe_name}.json"), "w") as f:
                        json.dump(t_def, f, indent=2)
                    
                    tool_names.append(safe_name)
                
                # Save the Index (Directory Listing)
                index = {
                    "server_name": server_name,
                    "description": f"Official tools for {server_name}.",
                    "tools": tool_names
                }
                with open(os.path.join(server_dir, "index.json"), "w") as f:
                    json.dump(index, f, indent=2)
                    
    except Exception as e:
        print(f"⚠️ Failed to fetch {server_name}: {e}")

async def build_registry():
    print("🔨 BUILDING TOOL REGISTRY (This may take 30s to download servers)...")
    if os.path.exists(REGISTRY_ROOT):
        shutil.rmtree(REGISTRY_ROOT)
    os.makedirs(REGISTRY_ROOT)

    # 1. SQLite (Database Tools) - Python package via uvx
    # We create a temp DB so the server starts successfully
    conn = sqlite3.connect(DB_FILE)
    conn.close()
    await fetch_and_save_server_tools("sqlite", "uvx", ["mcp-server-sqlite", "--db-path", DB_FILE])

    # 2. Filesystem (File Tools) - npm package via npx
    # Pass directories as positional args (not flags)
    await fetch_and_save_server_tools("filesystem", "npx", ["-y", "@modelcontextprotocol/server-filesystem", os.getcwd()])

    # 3. Git (Source Control Tools) - Python package via uvx
    # This gives us real 'git_status', 'git_commit', 'git_diff' tools
    await fetch_and_save_server_tools("git", "uvx", ["mcp-server-git", "--repository", GIT_REPO])

    # 4. Time (Utility Tools) - Python package via uvx
    await fetch_and_save_server_tools("time", "uvx", ["mcp-server-time"])

    # Cleanup temp file
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    print("\n✅ Registry Built! Folder Structure:")
    for root, dirs, files in os.walk(REGISTRY_ROOT):
        level = root.replace(REGISTRY_ROOT, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f"{indent}📂 {os.path.basename(root)}/")
        for f in files[:3]: # Limit print to 3 files per folder
            print(f"{indent}    📄 {f}")
        if len(files) > 3:
            print(f"{indent}    ... ({len(files)-3} more)")

# --- PHASE 2: THE DISCOVERY AGENT ---

def count_tokens(text):
    return len(str(text)) / 4

async def run_discovery_agent():
    print("\n🕵️ STARTING DISCOVERY AGENT...")
    
    # We use the Filesystem MCP to "Browse" the registry we just built
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", REGISTRY_ROOT],
        env=os.environ.copy()
    )

    #client = AsyncOpenAI()

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # SCENARIO: User asks "What time is it in Tokyo?"
            # The agent knows nothing. It must find the "time" tool.
            
            print("\n🤖 User Query: 'What time is it in Tokyo?'")
            total_tokens = 0
            
            # STEP 1: List Root Servers
            print("👉 Step 1: Agent listing ./servers root...")
            ls_root = await session.call_tool("list_directory", arguments={"path": REGISTRY_ROOT})
            root_content = str(ls_root.content)
            total_tokens += count_tokens(root_content)
            
            print(f"   Agent sees: {['sqlite', 'git', 'filesystem', 'time']}")
            print(f"   Token Cost: {int(count_tokens(root_content))}")

            # STEP 2: Agent picks 'time' folder
            target_path = os.path.join(REGISTRY_ROOT, "time")
            print(f"\n👉 Step 2: Agent checking '{target_path}'...")
            ls_time = await session.call_tool("list_directory", arguments={"path": target_path})
            
            # STEP 3: Agent reads 'get_current_time.json'
            # In a real agent loop, the LLM would pick this file based on the name
            tool_path = os.path.join(target_path, "get_current_time.json")
            print(f"\n👉 Step 3: Agent reading tool def '{tool_path}'...")
            read_tool = await session.call_tool("read_file", arguments={"path": tool_path})
            
            tool_content = str(read_tool.content)
            total_tokens += count_tokens(tool_content)
            
            print(f"✅ Loaded Tool Schema: {json.loads(read_tool.content[0].text)['name']}")
            print(f"✅ FINAL CONTEXT LOAD: ~{int(total_tokens)} tokens")
            
            # --- COMPARISON ---
            # Calculate cost if we had loaded ALL tools from ALL servers
            all_files_content = ""
            for root, _, files in os.walk(REGISTRY_ROOT):
                for f in files:
                    with open(os.path.join(root, f), "r") as tool_file:
                        all_files_content += tool_file.read()
            
            full_load_tokens = count_tokens(all_files_content)
            savings = ((full_load_tokens - total_tokens) / full_load_tokens) * 100
            
            print("\n" + "="*40)
            print(f" VS LOADING ALL TOOLS: ~{int(full_load_tokens)} tokens")
            print(f" EFFICIENCY GAIN:      {savings:.2f}%")
            print("="*40)

if __name__ == "__main__":
    asyncio.run(build_registry())
    asyncio.run(run_discovery_agent())