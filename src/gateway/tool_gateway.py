import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

class ToolExecutionGateway:
    def __init__(self, timeout_ms: int = 3000):
        self.timeout_seconds = timeout_ms / 1000.0

    async def execute(self, tool_func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Executes a given tool function within a sandbox subject to a hard timeout.
        If the tool takes longer than the timeout, it is cancelled and a synthetic error observation is returned.
        """
        try:
            # We use asyncio.wait_for to enforce the hard timeout
            result = await asyncio.wait_for(
                self._run_tool(tool_func, *args, **kwargs),
                timeout=self.timeout_seconds
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Tool execution timed out after {self.timeout_seconds}s")
            return {"error": "Tool execution timed out", "observation": "The requested tool exceeded the time limit."}
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return {"error": "Tool execution failed", "observation": str(e)}

    async def _run_tool(self, tool_func: Callable, *args: Any, **kwargs: Any) -> Any:
        if asyncio.iscoroutinefunction(tool_func):
            return await tool_func(*args, **kwargs)
        else:
            # Run blocking synchronous functions in a thread pool
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: tool_func(*args, **kwargs))
