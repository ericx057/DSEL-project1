import socket
import uvicorn
import asyncio
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.gateway.main import (
    app, get_access_matrix_repo, get_scope_repo, get_cache_repo,
    get_rate_limit_repo, get_audit_repo, get_model_hook, global_circuit_breaker
)
from src.gateway.models import AccessTier
from tests.gateway.mocks import (
    InMemoryAccessMatrixRepository, InMemoryScopeRepository,
    InMemoryCacheRepository, InMemoryRateLimitRepository, InMemoryAuditRepository
)
from src.gateway.model_hook import ModelHook

# --- Mock Model for the Demo ---
class DemoModelHook(ModelHook):
    def __init__(self, circuit_breaker=None):
        super().__init__(model_id="demo", circuit_breaker=circuit_breaker)
        
    async def generate_stream(self, prompt: str):
        # Provide a safe, isolated dummy response without hitting external APIs
        response = f"[Inference Mode] Analyzing query: '{prompt}'.\n" \
                   f"The system has identified 3 cross-file references related to this concept.\n" \
                   f"Proceeding with isolated synthesis based on T-3 Access Tier permissions..."
        
        for word in response.split(" "):
            await asyncio.sleep(0.08) # Simulate token generation speed
            yield word + " "
        
        if self.circuit_breaker:
            self.circuit_breaker.record_success()

# --- Apply Dependency Overrides so it runs without real databases ---
app.dependency_overrides[get_access_matrix_repo] = lambda: InMemoryAccessMatrixRepository({"user1": AccessTier.T3})
app.dependency_overrides[get_scope_repo] = lambda: InMemoryScopeRepository()
app.dependency_overrides[get_cache_repo] = lambda: InMemoryCacheRepository()
app.dependency_overrides[get_rate_limit_repo] = lambda: InMemoryRateLimitRepository()
app.dependency_overrides[get_audit_repo] = lambda: InMemoryAuditRepository()
app.dependency_overrides[get_model_hook] = lambda: DemoModelHook(global_circuit_breaker)

# --- Mount Static Frontend ---
# Expose the HTML at the root securely
@app.get("/")
async def serve_frontend():
    return FileResponse("src/frontend/index.html")

# --- Port Management and Server Boot ---
def is_port_in_use(port: int, host: str = '127.0.0.1') -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

def get_free_port(start_port=8000, max_port=8020, host='127.0.0.1'):
    """Finds the first available port, fulfilling the fallback requirement."""
    for port in range(start_port, max_port + 1):
        if not is_port_in_use(port, host):
            return port
    raise RuntimeError(f"All localhost ports between {start_port} and {max_port} are in use.")

if __name__ == "__main__":
    try:
        # Strictly bind to localhost to "close the port to not allow injections" via external network
        host = "127.0.0.1"
        port = get_free_port(host=host)
        print(f"\n" + "="*50)
        print(f"CIS DEMO SERVER STARTING")
        print(f"Security: Port strictly bound to {host} (Closed to external access)")
        print(f"URL: http://{host}:{port}/")
        print(f"="*50 + "\n")
        
        uvicorn.run(app, host=host, port=port, log_level="info")
        
    except RuntimeError as e:
        print(f"CRITICAL ERROR: {e}")
        exit(1)
