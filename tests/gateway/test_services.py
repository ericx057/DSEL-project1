import pytest
import time
from src.gateway.services import CircuitBreaker

def test_circuit_breaker_success():
    cb = CircuitBreaker(failure_threshold=2)
    assert cb.is_allowed() is True
    cb.record_success()
    assert cb.state == "CLOSED"

def test_circuit_breaker_failure_and_recovery():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    
    cb.record_failure()
    assert cb.state == "CLOSED"
    assert cb.is_allowed() is True
    
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.is_allowed() is False
    
    # Wait for recovery
    time.sleep(0.15)
    assert cb.is_allowed() is True # Transitions to HALF_OPEN
    assert cb.state == "HALF_OPEN"
    
    # In HALF_OPEN, it's allowed
    assert cb.is_allowed() is True

def test_circuit_breaker_half_open_failure():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
    cb.record_failure()
    assert cb.state == "OPEN"
    time.sleep(0.15)
    assert cb.is_allowed() is True
    cb.record_failure()
    assert cb.state == "OPEN"
