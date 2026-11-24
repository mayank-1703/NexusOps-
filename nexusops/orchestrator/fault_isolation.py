"""Circuit breaker, retry policy, and fault isolation primitives for NexusOps."""

import asyncio
from enum import Enum
import logging
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("nexusops.orchestrator.fault_isolation")


class CircuitState(str, Enum):
    """Circuit breaker operational state."""

    CLOSED = "CLOSED"  # Healthy, requests proceed
    OPEN = "OPEN"  # Tripped, requests fail fast
    HALF_OPEN = "HALF_OPEN"  # Testing recovery


class CircuitBreaker:
    """Circuit breaker preventing cascading failures across infrastructure nodes and upstream MCP servers."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()
        self._lock = asyncio.Lock()

    async def can_execute(self) -> bool:
        """Evaluate if requests can execute or should fail fast."""
        async with self._lock:
            now = time.time()
            if self.state == CircuitState.OPEN:
                if now - self.last_failure_time > self.recovery_timeout_seconds:
                    logger.info("Circuit breaker '%s' entering HALF_OPEN state.", self.name)
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False
            return True

    async def record_success(self):
        """Record successful call and reset failure counters."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker '%s' recovered to CLOSED state.", self.name)
            self.state = CircuitState.CLOSED
            self.failure_count = 0

    async def record_failure(self):
        """Record failure and trip circuit if threshold exceeded."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                if self.state != CircuitState.OPEN:
                    logger.warning(
                        "Circuit breaker '%s' TRIPPED to OPEN state after %d failures.",
                        self.name,
                        self.failure_count,
                    )
                self.state = CircuitState.OPEN


class FaultIsolationBoundary:
    """Executes operations inside an isolated boundary with circuit breaker, timeout, and error trapping."""

    def __init__(
        self,
        target_name: str,
        circuit_breaker: Optional[CircuitBreaker] = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 1,
    ):
        self.target_name = target_name
        self.circuit_breaker = circuit_breaker or CircuitBreaker(name=target_name)
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    async def execute(self, func: Callable, *args, **kwargs) -> Dict[str, Any]:
        """Safely execute callable within the fault isolation boundary."""
        start_time = time.time()

        # Check circuit breaker
        if not await self.circuit_breaker.can_execute():
            duration_ms = (time.time() - start_time) * 1000
            return {
                "success": False,
                "target": self.target_name,
                "error": f"Circuit breaker OPEN for target '{self.target_name}'. Requests failing fast.",
                "circuit_state": self.circuit_breaker.state.value,
                "duration_ms": round(duration_ms, 2),
            }

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await asyncio.wait_for(func(*args, **kwargs), timeout=self.timeout_seconds)
                else:
                    loop = asyncio.get_running_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda: func(*args, **kwargs)),
                        timeout=self.timeout_seconds,
                    )

                await self.circuit_breaker.record_success()
                duration_ms = (time.time() - start_time) * 1000
                return {
                    "success": True,
                    "target": self.target_name,
                    "result": result,
                    "circuit_state": self.circuit_breaker.state.value,
                    "duration_ms": round(duration_ms, 2),
                    "attempts": attempt + 1,
                }

            except asyncio.TimeoutError:
                last_error = f"Execution timed out after {self.timeout_seconds}s"
                await self.circuit_breaker.record_failure()
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {str(exc)}"
                await self.circuit_breaker.record_failure()

            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (2**attempt))

        duration_ms = (time.time() - start_time) * 1000
        return {
            "success": False,
            "target": self.target_name,
            "error": last_error,
            "circuit_state": self.circuit_breaker.state.value,
            "duration_ms": round(duration_ms, 2),
            "attempts": self.max_retries + 1,
        }
