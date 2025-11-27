"""
Token Comparison Runner
Runs both traditional and code mode approaches and compares token usage.
"""
import asyncio
import subprocess
import sys

async def run_mode(script_name, mode_name):
    """Run a mode script and capture output."""
    print(f"\n{'='*70}")
    print(f"🚀 Running {mode_name}...")
    print(f"{'='*70}\n")
    
    result = subprocess.run(
        [sys.executable, script_name],
        capture_output=True,
        text=True,
        cwd="."
    )
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.stdout

async def main():
    print("MCP TOOL ACCESS: TOKEN USAGE COMPARISON")
    print("="*70)
    print("\nThis comparison tests two approaches:")
    print("1. TRADITIONAL: All MCP tools loaded directly in LLM context")
    print("2. CODE MODE: LLM discovers and calls tools via Python code")
    print("\nTask: Create project status report with git info, file count, and timestamp")
    print("="*70)
    
    # Run traditional mode
    traditional_output = await run_mode("traditional_mode.py", "TRADITIONAL MODE")
    
    # Run code mode
    code_output = await run_mode("code_mode.py", "CODE MODE")
    
    # Extract and display comparison
    print("\n" + "="*70)
    print(" FINAL COMPARISON")
    print("="*70)
    
    # Parse results (simplified - could be more robust)
    for line in traditional_output.split('\n'):
        if 'TRADITIONAL MODE TOKEN USAGE' in line or 'Total' in line or 'Input' in line or 'Output' in line or 'Tools in Context' in line:
            print(line)
    
    print("\nvs\n")
    
    for line in code_output.split('\n'):
        if 'CODE MODE TOKEN USAGE' in line or 'Total' in line or 'Input' in line or 'Output' in line or 'Tools in Context' in line:
            print(line)
    

if __name__ == "__main__":
    asyncio.run(main())
