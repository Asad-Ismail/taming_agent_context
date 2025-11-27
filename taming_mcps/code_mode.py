"""
Code Mode - LLM generates Python code that calls MCP tools.
Run build_registry.py first to create the ./servers/ directory.
"""
import os
import json
import asyncio
import contextlib
import io
from openai import AsyncOpenAI
from dotenv import load_dotenv, find_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

model_name = "gpt-4o-mini" 
# --- THE EXECUTION ENVIRONMENT (Sandbox) ---
async def execute_code(code: str, globals_dict: dict, locals_dict: dict) -> str:
    """Execute Python code with async support and capture output."""
    output_capture = io.StringIO()
    try:
        with contextlib.redirect_stdout(output_capture):
            globals_dict["__builtins__"] = __builtins__
            
            # If code has 'await', wrap in async function
            if 'await' in code:
                code_lines = code.strip().split('\n')
                # Make last line return if it's an expression
                if code_lines and not code_lines[-1].strip().startswith(('import', 'from', 'print(', '#')):
                    code_lines[-1] = f"return {code_lines[-1]}"
                
                indented = '\n    '.join(code_lines)
                wrapped = f"async def _run():\n    {indented}\n\n__result = _run()"
                exec(wrapped, globals_dict, locals_dict)
                result_val = await locals_dict['__result']
                if result_val is not None:
                    print(repr(result_val))
            else:
                # Sync code
                exec(code, globals_dict, locals_dict)
                lines = [l.strip() for l in code.split('\n') if l.strip() and not l.strip().startswith('#')]
                if lines and not lines[-1].startswith(('import', 'from', 'print(')):
                    try:
                        val = eval(lines[-1], globals_dict, locals_dict)
                        if val is not None:
                            print(repr(val))
                    except:
                        pass
        
        # Merge locals back into globals so imports and variables persist
        globals_dict.update(locals_dict)
        
        result = output_capture.getvalue()
        return result if result else "Code executed successfully (no output)."
        
    except Exception as e:
        return f"Execution Error: {e}"

async def start_mcp_servers(stack: contextlib.AsyncExitStack):
    """Start all MCP servers and register them in the bridge."""
    import mcp_bridge
    
    servers = [
        ("time", "uvx", ["mcp-server-time"]),
        ("git", "uvx", ["mcp-server-git", "--repository", os.path.dirname(os.getcwd())]),
    ]
    
    for name, cmd, args in servers:
        try:
            params = StdioServerParameters(command=cmd, args=args, env=os.environ.copy())
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            mcp_bridge.ACTIVE_SESSIONS[name] = session
            print(f"   Connected to '{name}' server")
        except Exception as e:
            print(f"   Warning: Could not connect to '{name}': {e}")

async def run_agent_executor():
    """
    The Agent Loop. 
    The Agent is given a 'run_python' tool to execute code.
    It must explore ./servers to discover and use available tools.
    """
    
    print("Establishing persistent connections to MCP servers...")
    stack = contextlib.AsyncExitStack()
    
    try:
        await start_mcp_servers(stack)

        # Agent Setup
        client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE")
        )
        
        system_prompt = """
        You are a Python agent with access to MCP tools through the ./servers/ directory.
        You are ALREADY running in an async context - use 'await' directly, never asyncio.run().
        
        MANDATORY WORKFLOW:
        Step 1: ALWAYS start by discovering available servers
        Step 2: Explore relevant server directories to find tools
        Step 3: Read tool documentation to understand usage
        Step 4: Import and use the appropriate tool
        
        EXAMPLE WORKFLOW:
        ```python
        # Step 1: Discover servers
        import os
        print(os.listdir('./servers'))
        ```
        
        Then in next code block:
        ```python
        # Step 2: Explore a relevant server
        print(os.listdir('./servers/<server_name>'))
        ```
        
        Then:
        ```python
        # Step 3: Check tool documentation
        exec(open('./servers/<server>/<tool>.py').read())
        help(<tool_function>)
        ```
        
        Finally:
        ```python
        # Step 4: Use the tool
        import sys
        sys.path.insert(0, './servers/<server_name>')
        from <tool_file> import <tool_function>
        result = await <tool_function>({<arguments>})
        print(result)
        ```
        
        ABSOLUTE PROHIBITIONS:
        ❌ NEVER import datetime, time, pytz, or other stdlib modules to solve tasks
        ❌ NEVER implement solutions yourself - ALWAYS use MCP tools from ./servers/
        ❌ NEVER skip the discovery phase - you MUST explore ./servers/ first
        ❌ DO NOT assume what tools exist - discover them every time
        
        CRITICAL RULES:
        - You are in an async context - use 'await', NEVER asyncio.run()
        - Imports persist across code blocks - import once, use many times
        - All MCP tools are async functions taking a dict argument
        - Add server directory to sys.path before importing
        """

        user_query = """Get Current Time of Amsterdam"""

        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{user_query}\n\nREMINDER: Start by discovering what's in ./servers/ directory. DO NOT use datetime/time modules."}
        ]

        print(f"\nUSER: {user_query}")
        print("-" * 50)

        # Persistent execution environment
        import mcp_bridge
        persistent_globals = {"os": os, "asyncio": asyncio, "json": json, "mcp_bridge": mcp_bridge}
        persistent_locals = {}

        total_input_tokens = 0
        total_output_tokens = 0
        turn_count = 0

        # Agent Loop
        for turn in range(8): # max 8 turns
            turn_count += 1
            
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0,
                tools=[{
                    "type": "function",
                    "function": {
                        "name": "run_python",
                        "description": "Executes Python code. Available tools are in ./servers/ directory. Import from there to use MCP tools.",
                        "parameters": {
                            "type": "object",
                            "properties": {"code": {"type": "string", "description": "Python code to execute. Can import from ./servers/ to access MCP tools."}},
                            "required": ["code"]
                        }
                    }
                }]
            )
            
            # Track tokens
            if hasattr(response, 'usage'):
                total_input_tokens += response.usage.prompt_tokens
                total_output_tokens += response.usage.completion_tokens
                print(f"\nTurn {turn_count} - Input: {response.usage.prompt_tokens}, Output: {response.usage.completion_tokens}")
            
            msg = response.choices[0].message
            messages.append(msg)

            # Check if agent is done
            if not msg.tool_calls:
                if msg.content and ("<Answer>" in msg.content or turn == 7):
                    print(f"\nAGENT: {msg.content}")
                break

            # Execute tool calls
            for tool_call in msg.tool_calls:
                code = json.loads(tool_call.function.arguments)["code"]
                print(f"\nAGENT WROTE CODE:\n{code}")
                
                # Execute code and capture output
                result = await execute_code(code, persistent_globals, persistent_locals)
                print(f"OUTPUT: {result.strip()}")
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

        print("\n" + "="*60)
        print(f"CODE MODE TOKEN USAGE:")
        print(f"   Total Turns: {turn_count}")
        print(f"   Input Tokens: {total_input_tokens:,}")
        print(f"   Output Tokens: {total_output_tokens:,}")
        print(f"   Total Tokens: {(total_input_tokens + total_output_tokens):,}")
        print(f"   Tools in Context: 1 (run_python)")
        print("="*60)

    finally:
        await stack.aclose()

async def main():
    # Check if registry exists
    if not os.path.exists("./servers"):
        print("Warning: Registry not found. Please run 'python build_registry.py' first.")
        return
    
    await run_agent_executor()

if __name__ == "__main__":
    asyncio.run(main())