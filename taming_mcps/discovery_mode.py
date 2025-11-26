"""
Discovery Mode: Agent discovers and uses MCP tools through structured exploration
This is closer to the real Anthropic/Cloudflare pattern - no code execution!
"""
import os
import json
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv, find_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv(find_dotenv())
REGISTRY_ROOT = os.path.abspath("./servers")

async def main():
    print("🔌 Connecting to MCP servers for discovery...")
    
    # Connect to Time MCP server
    time_params = StdioServerParameters(
        command="uvx",
        args=["mcp-server-time"],
        env=os.environ.copy()
    )
    
    async with stdio_client(time_params) as (time_read, time_write):
        async with ClientSession(time_read, time_write) as time_session:
            await time_session.initialize()
            
            # Get available tools from the server
            tools_list = await time_session.list_tools()
            
            # Convert MCP tools to OpenAI function calling format
            openai_tools = []
            for tool in tools_list.tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": f"mcp_time_{tool.name}",
                        "description": tool.description,
                        "parameters": tool.inputSchema
                    }
                })
            
            print(f"✅ Connected to Time server with {len(openai_tools)} tools")
            
            # Initialize OpenAI client
            api_key = os.getenv("OPENAI_API_KEY")
            api_base = os.getenv("OPENAI_API_BASE")
            client = AsyncOpenAI(api_key=api_key, base_url=api_base)
            
            # Agent conversation
            user_query = "What time is it in Tokyo right now?"
            print(f"\n🤖 USER: {user_query}")
            print("-" * 50)
            
            messages = [
                {"role": "user", "content": user_query}
            ]
            
            # Agent loop
            for turn in range(3):
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    tools=openai_tools,
                    tool_choice="auto"
                )
                
                msg = response.choices[0].message
                messages.append(msg)
                
                if msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        tool_name = tool_call.function.name.replace("mcp_time_", "")
                        args = json.loads(tool_call.function.arguments)
                        
                        print(f"\n🔧 Agent calling MCP tool: {tool_name}")
                        print(f"   Arguments: {args}")
                        
                        # Call the actual MCP tool
                        result = await time_session.call_tool(tool_name, arguments=args)
                        
                        # Extract result
                        if result.content and len(result.content) > 0:
                            result_text = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
                        else:
                            result_text = str(result)
                        
                        print(f"   Result: {result_text}")
                        
                        # Add tool result to messages
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result_text
                        })
                    
                    # Continue conversation with tool results
                    continue
                
                # Final answer
                if msg.content:
                    print(f"\n✅ AGENT: {msg.content}")
                    break

if __name__ == "__main__":
    asyncio.run(main())
