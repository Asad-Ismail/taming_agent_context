"""
Traditional Mode - LLM has direct access to all MCP tools.
Compare token usage with code_mode.py approach.
"""
import os
import json
import asyncio
import contextlib
from openai import AsyncOpenAI
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

async def start_mcp_servers(stack: contextlib.AsyncExitStack):
    """Start all MCP servers and return sessions with their tools."""
    # Use the SAME server configs as build_registry.py for fair comparison
    servers = [
        ("time", "uvx", ["mcp-server-time"]),
        ("sqlite", "uvx", ["mcp-server-sqlite", "--db-path", "temp_comparison.db"]),
        ("git", "uvx", ["mcp-server-git", "--repository", os.path.dirname(os.getcwd())]),
        ("github", "npx", ["-y", "@modelcontextprotocol/server-github"]),
        ("filesystem", "npx", ["-y", "@modelcontextprotocol/server-filesystem", os.path.dirname(os.getcwd())]),
    ]
    
    sessions = {}
    all_tools = []
    
    print("🔌 Connecting to MCP servers (loading ALL tools for traditional mode)...")
    
    for name, cmd, args in servers:
        try:
            params = StdioServerParameters(command=cmd, args=args, env=os.environ.copy())
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            
            # Get tools from this server
            tools_response = await session.list_tools()
            sessions[name] = session
            
            # Convert MCP tools to OpenAI function format
            for tool in tools_response.tools:
                tool_def = tool.model_dump()
                openai_tool = {
                    "type": "function",
                    "function": {
                        "name": f"{name}_{tool_def['name']}",
                        "description": tool_def.get('description', 'No description'),
                        "parameters": tool_def.get('inputSchema', {
                            "type": "object",
                            "properties": {}
                        })
                    }
                }
                all_tools.append({
                    "server": name,
                    "tool_name": tool_def['name'],
                    "openai_def": openai_tool
                })
            
            print(f"   ✅ Connected to '{name}' ({len(tools_response.tools)} tools)")
        except Exception as e:
            print(f"   ⚠️ Could not connect to '{name}': {e}")
    
    return sessions, all_tools

async def run_traditional_agent():
    """Run agent with all MCP tools directly available."""
    
    stack = contextlib.AsyncExitStack()
    
    try:
        sessions, all_tools = await start_mcp_servers(stack)
        print()

        client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE")
        )
        
        system_prompt = """You are a helpful assistant with access to various tools.
    Use the available tools to complete the user's request."""
        '''
        user_query = """Create a summary report file named 'project_status.txt' with:
        Current git branch and last commit message
        Total number of Python files in the project
        Current timestamp

        Save it in the project root directory."""
        '''

        user_query = "What time is it in Amsterdam right now?"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]

        print(f"🤖 USER: {user_query.strip()}")
        print("-" * 50)

        # Prepare OpenAI tools list
        openai_tools = [tool_info["openai_def"] for tool_info in all_tools]
        
        print(f"\n📊 Total tools available: {len(openai_tools)}")
        
        total_input_tokens = 0
        total_output_tokens = 0
        turn_count = 0

        # Agent loop
        for turn in range(15):
            turn_count += 1
            
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0,
                tools=openai_tools
            )
            
            # Track tokens
            if hasattr(response, 'usage'):
                total_input_tokens += response.usage.prompt_tokens
                total_output_tokens += response.usage.completion_tokens
                print(f"\n Turn {turn_count} - Input: {response.usage.prompt_tokens}, Output: {response.usage.completion_tokens}")
            
            msg = response.choices[0].message
            messages.append(msg)

            if not msg.tool_calls:
                print(f"\n AGENT: {msg.content or 'Done'}")
                break

            # Execute tool calls
            for tool_call in msg.tool_calls:
                function_name = tool_call.function.name
                
                # Find the tool info
                tool_info = None
                for t in all_tools:
                    if f"{t['server']}_{t['tool_name']}" == function_name:
                        tool_info = t
                        break
                
                if not tool_info:
                    print(f"⚠️ Unknown tool: {function_name}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Error: Unknown tool {function_name}"
                    })
                    continue
                
                try:
                    args = json.loads(tool_call.function.arguments)
                    print(f"\n🔧 Calling {function_name}({args})")
                    
                    # Call the actual MCP tool
                    session = sessions[tool_info['server']]
                    result = await session.call_tool(tool_info['tool_name'], arguments=args)
                    
                    # Extract content
                    if hasattr(result, 'content'):
                        if isinstance(result.content, list):
                            content = '\n'.join(
                                item.text if hasattr(item, 'text') else str(item)
                                for item in result.content
                            )
                        else:
                            content = str(result.content)
                    else:
                        content = str(result)
                    
                    print(f" Result: {content[:200]}...")
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": content
                    })
                    
                except Exception as e:
                    print(f"⚠️ Error calling {function_name}: {e}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Error: {e}"
                    })

        print("\n" + "="*60)
        print(f" TRADITIONAL MODE TOKEN USAGE:")
        print(f"   Total Turns: {turn_count}")
        print(f"   Input Tokens: {total_input_tokens:,}")
        print(f"   Output Tokens: {total_output_tokens:,}")
        print(f"   Total Tokens: {(total_input_tokens + total_output_tokens):,}")
        print(f"   Tools in Context: {len(openai_tools)}")
        print("="*60)

    finally:
        await stack.aclose()

async def main():
    await run_traditional_agent()

if __name__ == "__main__":
    asyncio.run(main())
