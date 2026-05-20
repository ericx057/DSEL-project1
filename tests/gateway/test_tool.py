import asyncio
import pytest
from src.gateway.tool_gateway import ToolExecutionGateway

@pytest.mark.asyncio
async def test_tool_execution_success():
    gateway = ToolExecutionGateway(timeout_ms=3000)
    
    async def fast_tool(x):
        return x * 2
        
    result = await gateway.execute(fast_tool, 5)
    assert result == 10

@pytest.mark.asyncio
async def test_tool_execution_timeout():
    # Very short timeout for the test
    gateway = ToolExecutionGateway(timeout_ms=50)
    
    async def slow_tool():
        await asyncio.sleep(0.1)
        return "done"
        
    result = await gateway.execute(slow_tool)
    assert isinstance(result, dict)
    assert "error" in result
    assert result["error"] == "Tool execution timed out"

@pytest.mark.asyncio
async def test_tool_execution_exception():
    gateway = ToolExecutionGateway(timeout_ms=3000)
    
    async def crashing_tool():
        raise ValueError("Simulated crash")
        
    result = await gateway.execute(crashing_tool)
    assert isinstance(result, dict)
    assert "error" in result
    assert result["error"] == "Tool execution failed"

@pytest.mark.asyncio
async def test_sync_tool_execution():
    gateway = ToolExecutionGateway(timeout_ms=3000)
    
    def sync_tool():
        return "sync done"
        
    result = await gateway.execute(sync_tool)
    assert result == "sync done"
