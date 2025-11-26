import os
import json
import asyncio
import shutil
import sqlite3
from openai import AsyncOpenAI
from dotenv import load_dotenv, find_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Load environment variables
load_dotenv(find_dotenv())

# --- CONFIGURATION ---
REGISTRY_ROOT = os.path.abspath("./servers")
DB_FILE = "temp_schema.db"
# Use parent directory as Git repo (current folder might be a subdirectory)
GIT_REPO = os.path.abspath(os.path.join(os.getcwd(), ".."))

# ---  BUILD THE REGISTRY FROM LIVE SERVERS ---

async def fetch_and_save_server_tools(server_name, command, args, env=None):
    """
    Boots a REAL MCP server, asks for its tools, and saves them 
    into the blog's specific folder structure: ./servers/{name}/{tool}.json
    """
    server_dir = os.path.join(REGISTRY_ROOT, server_name)
    if os.path.exists(server_dir):
        shutil.rmtree(server_dir)
    os.makedirs(server_dir)
    
    print(f" Connecting to live '{server_name}' server...")
    
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

    await asyncio.gather(
    fetch_and_save_server_tools("sqlite", "uvx", ["mcp-server-sqlite", "--db-path", DB_FILE]),
    fetch_and_save_server_tools("filesystem", "npx", ["-y", "@modelcontextprotocol/server-filesystem", os.getcwd()]),
    fetch_and_save_server_tools("git", "uvx", ["mcp-server-git", "--repository", GIT_REPO]),
    fetch_and_save_server_tools("time", "uvx", ["mcp-server-time"]))

    # Cleanup temp file
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    print("\n Registry Built! Folder Structure:")
    for root, dirs, files in os.walk(REGISTRY_ROOT):
        level = root.replace(REGISTRY_ROOT, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f"{indent}📂 {os.path.basename(root)}/")
        for f in files[:3]: # Limit print to 3 files per folder
            print(f"{indent}    📄 {f}")
        if len(files) > 3:
            print(f"{indent}    ... ({len(files)-3} more)")

# --- THE DISCOVERY AGENT ---

def estimate_tokens(text):
    """Rough estimate for context that isn't sent to API yet"""
    return len(str(text)) / 4

async def compare_discovery_agent():
    print("\nSTARTING DISCOVERY AGENT WITH LLM...")
    
    # Initialize OpenAI client
    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE")
    client = AsyncOpenAI(api_key=api_key, base_url=api_base)
    
    # SCENARIO: User asks "What time is it in Tokyo?"
    user_query = "What time is it in Tokyo?"
    print(f"\n User Query: '{user_query}'")


    print("\n" + "="*60)
    print("CASE 1: SMART DISCOVERY - LLM navigates tool registry")
    print("="*60)
    
    discovered_tokens = 0
    
    # LLM sees available server categories
    # Dynamically discover all servers in the registry
    server_indices = {}
    for server_name in os.listdir(REGISTRY_ROOT):
        server_path = os.path.join(REGISTRY_ROOT, server_name)
        if os.path.isdir(server_path):
            index_path = os.path.join(server_path, "index.json")
            if os.path.exists(index_path):
                with open(index_path, "r") as f:
                    server_indices[server_name] = json.load(f)
    
    # Build server list dynamically
    server_list_lines = ["Available tool servers:"]
    for server_name, index in server_indices.items():
        server_list_lines.append(f"    - {server_name}: {index['description']}")
    server_list = "\n".join(server_list_lines)
    
    context_tokens_estimate = estimate_tokens(server_list)
    
    print(f" LLM sees server categories (~{int(context_tokens_estimate)} tokens estimated)")
    
    # Ask LLM to pick the right server
    response1 = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a tool discovery assistant. Given a user query, identify which tool server category would be most relevant. Respond with only the server name."},
            {"role": "user", "content": f"User query: {user_query}\n\n{server_list}\n\nWhich server should I use?"}
        ]
    )
    
    selected_server = response1.choices[0].message.content.strip().lower()
    discovered_tokens += response1.usage.total_tokens
    
    print(f"   LLM selected: '{selected_server}'")
    print(f"   Actual API tokens: {response1.usage.total_tokens} (prompt: {response1.usage.prompt_tokens}, completion: {response1.usage.completion_tokens})")
    
    #  Load tools from selected server
    with open(os.path.join(REGISTRY_ROOT, selected_server, "index.json"), "r") as f:
        server_index = json.load(f)
    
    tools_list = "\n".join([f"- {tool}" for tool in server_index['tools']])
    context_tokens_estimate = estimate_tokens(tools_list)
    
    print(f"\n LLM sees tools in '{selected_server}' (~{int(context_tokens_estimate)} tokens estimated)")
    
    # Ask LLM to pick the right tool
    response2 = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a tool discovery assistant. Given a user query, identify which specific tool would be most relevant. Respond with only the tool name."},
            {"role": "user", "content": f"User query: {user_query}\n\nAvailable tools:\n{tools_list}\n\nWhich tool should I use?"}
        ]
    )
    
    selected_tool = response2.choices[0].message.content.strip()
    discovered_tokens += response2.usage.total_tokens
    
    print(f"   LLM selected: '{selected_tool}'")
    print(f"   Actual API tokens: {response2.usage.total_tokens} (prompt: {response2.usage.prompt_tokens}, completion: {response2.usage.completion_tokens})")
    
    # Step 3: Load the selected tool's full definition
    tool_path = os.path.join(REGISTRY_ROOT, selected_server, f"{selected_tool}.json")
    with open(tool_path, 'r') as f:
        tool_def = f.read()
    
    tool_def_tokens = estimate_tokens(tool_def)
    
    print(f"\n👉 Step 3: Load full tool definition (~{int(tool_def_tokens)} tokens estimated)")
    print(f" SMART DISCOVERY TOTAL: {int(discovered_tokens)} actual API tokens")
    
    # Now actually call the tool with the discovered tool definition using function calling
    print(f"\n👉 Step 4: Call LLM with discovered tool (using function calling)")
    
    tool_data = json.loads(tool_def)
    
    response3 = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": user_query}
        ],
        tools=[{
            "type": "function",
            "function": {
                "name": tool_data["name"],
                "description": tool_data["description"],
                "parameters": tool_data["inputSchema"]
            }
        }],
        tool_choice="auto"
    )
    
    discovered_tokens += response3.usage.total_tokens
    
    # Check if LLM wants to call the tool
    if response3.choices[0].message.tool_calls:
        tool_call = response3.choices[0].message.tool_calls[0]
        print(f"   LLM called tool: {tool_call.function.name}")
        print(f"   With arguments: {tool_call.function.arguments}")
        answer_smart = f"Tool call: {tool_call.function.name}({tool_call.function.arguments})"
    else:
        answer_smart = response3.choices[0].message.content
        print(f"   LLM Answer: {answer_smart}")
    
    print(f"   Actual API tokens: {response3.usage.total_tokens} (prompt: {response3.usage.prompt_tokens}, completion: {response3.usage.completion_tokens})")
    print(f" SMART DISCOVERY TOTAL: {int(discovered_tokens)} actual API tokens")
    
    # --- CASE 2: Naive Approach (Load ALL tools upfront) ---
    print("\n" + "="*60)
    print("CASE 2: NAIVE APPROACH - Load all tools upfront")
    print("="*60)
    
    naive_tokens = 0
    
    # Load all tool definitions
    all_tools = []
    for root, _, files in os.walk(REGISTRY_ROOT):
        for f in files:
            if f.endswith('.json') and f != 'index.json':
                with open(os.path.join(root, f), "r") as tool_file:
                    all_tools.append(tool_file.read())
    
    all_tools_str = "\n\n".join(all_tools)
    estimated_context = estimate_tokens(all_tools_str)
    print(f"Loading ALL tool definitions: ~{int(estimated_context)} tokens estimated")
    
    # Call LLM with ALL tools at once using function calling
    print(f"\n👉 Call LLM with ALL tools (using function calling)")
    
    # Convert all tool definitions to OpenAI function format
    all_tools_funcs = []
    for tool_str in all_tools:
        tool_json = json.loads(tool_str)
        all_tools_funcs.append({
            "type": "function",
            "function": {
                "name": tool_json["name"],
                "description": tool_json["description"],
                "parameters": tool_json["inputSchema"]
            }
        })
    
    response_naive = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": user_query}
        ],
        tools=all_tools_funcs,
        tool_choice="auto"
    )
    
    naive_tokens = response_naive.usage.total_tokens
    
    # Check if LLM wants to call a tool
    if response_naive.choices[0].message.tool_calls:
        tool_call = response_naive.choices[0].message.tool_calls[0]
        print(f"   LLM called tool: {tool_call.function.name}")
        print(f"   With arguments: {tool_call.function.arguments}")
        answer_naive = f"Tool call: {tool_call.function.name}({tool_call.function.arguments})"
    else:
        answer_naive = response_naive.choices[0].message.content
        print(f"   LLM Answer: {answer_naive}")


    assert answer_smart == answer_naive, "Answers from both approaches should match!"

    print(f"   Actual API tokens: {naive_tokens} (prompt: {response_naive.usage.prompt_tokens}, completion: {response_naive.usage.completion_tokens})")
    print(f" NAIVE APPROACH TOTAL: {int(naive_tokens)} actual API tokens")

    
    # --- COMPARISON ---
    savings = ((naive_tokens - discovered_tokens) / naive_tokens) * 100
    
    print("\n" + "="*60)
    print("RESULTS COMPARISON")
    print("="*60)
    print(f"Smart Discovery Total:       {int(discovered_tokens)} tokens (actual)")
    print(f"Naive Approach Total:        {int(naive_tokens)} tokens (actual)")
    print(f"Token Savings:               {int(naive_tokens - discovered_tokens)} tokens")
    print(f"Efficiency Gain:             {savings:.2f}%")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(build_registry())
    asyncio.run(compare_discovery_agent())