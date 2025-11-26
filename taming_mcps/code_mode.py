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
            print(f"   ✅ Connected to '{name}' server")
        except Exception as e:
            print(f"   ⚠️ Could not connect to '{name}': {e}")

async def run_agent_executor():
    """
    The Agent Loop. 
    The Agent is given a 'run_python' tool to execute code.
    It must explore ./servers to discover and use available tools.
    """
    
    print("🔌 Establishing persistent connections to MCP servers...")
    stack = contextlib.AsyncExitStack()
    
    try:
        await start_mcp_servers(stack)

        # Agent Setup
        client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE")
        )
        
        system_prompt = """
        You are a Python agent. Tools are available in `./servers/`.
        
        MANDATORY: Your FIRST step for ANY task is:
        ```python
        import os
        print(os.listdir('./servers'))
        ``` 
        Then navigate to the relevant tool, read the required tools .py files, and use them.
        All tools are async - use `await` when calling them.
        
        Never write code from scratch if a tool exists in ./servers/.
        Give Answer in <Answer></Answer> tags finally.
        """

        user_query = "What time is it in Amsterdam right now?"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{user_query}\n\nIMPORTANT: Pay close attention to the instructions in the system prompt."}
        ]

        print(f"\n🤖 USER: {user_query}")
        print("-" * 50)

        # Persistent execution environment
        persistent_globals = {"os": os, "asyncio": asyncio, "json": json}
        persistent_locals = {}

        # Agent Loop
        for turn in range(8): # max 8 turns
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=[{
                    "type": "function",
                    "function": {
                        "name": "run_python",
                        "description": "Executes Python code. Use search_tools(query, detail) to find MCP tools.",
                        "parameters": {
                            "type": "object",
                            "properties": {"code": {"type": "string"}},
                            "required": ["code"]
                        }
                    }
                }]
            )
            
            msg = response.choices[0].message
            messages.append(msg)

            if not msg.tool_calls and "<Answer>" in msg.content:
                print(f"🤖 AGENT: {msg.content}")
                break

            for tool_call in msg.tool_calls:
                code = json.loads(tool_call.function.arguments)["code"]
                print(f"\n📝 AGENT WROTE CODE:\n{code}")
                
                # Execute code and capture output
                result = await execute_code(code, persistent_globals, persistent_locals)
                print(f"💻 OUTPUT: {result.strip()}")
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

    finally:
        await stack.aclose()

async def main():
    # Check if registry exists
    if not os.path.exists("./servers"):
        print("⚠️  Registry not found. Please run 'python build_registry.py' first.")
        return
    
    await run_agent_executor()

if __name__ == "__main__":
    asyncio.run(main())