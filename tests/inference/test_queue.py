import pytest
import threading
import time
from inference.queue import RequestQueue, ServiceUnavailableError

def test_request_queue_success():
    queue = RequestQueue(max_concurrent=1, max_queue_depth=1)
    with queue.request():
        assert queue.active_requests == 1
        assert queue.queue_depth == 0

def test_request_queue_full():
    queue = RequestQueue(max_concurrent=1, max_queue_depth=1)
    
    def lock_queue():
        with queue.request():
            time.sleep(0.1)
            
    t1 = threading.Thread(target=lock_queue)
    t1.start()
    
    time.sleep(0.02) # Let t1 acquire
    
    def wait_queue():
        with queue.request():
            pass
            
    t2 = threading.Thread(target=wait_queue)
    t2.start()
    
    time.sleep(0.02) # Let t2 queue
    
    with pytest.raises(ServiceUnavailableError):
        with queue.request():
            pass
            
    t1.join()
    t2.join()
