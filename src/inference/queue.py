import threading
from contextlib import contextmanager

class ServiceUnavailableError(Exception):
    pass

class RequestQueue:
    def __init__(self, max_concurrent: int, max_queue_depth: int):
        self.max_concurrent = max_concurrent
        self.max_queue_depth = max_queue_depth
        self.active_requests = 0
        self.queue_depth = 0
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)

    @contextmanager
    def request(self):
        with self.lock:
            if self.active_requests >= self.max_concurrent:
                if self.queue_depth >= self.max_queue_depth:
                    raise ServiceUnavailableError("503 Service Unavailable: Queue Full")
                self.queue_depth += 1
                while self.active_requests >= self.max_concurrent:
                    self.condition.wait()
                self.queue_depth -= 1
            self.active_requests += 1

        try:
            yield
        finally:
            with self.lock:
                self.active_requests -= 1
                self.condition.notify()
