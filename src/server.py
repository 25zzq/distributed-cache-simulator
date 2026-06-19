from uuid import uuid4 as randomid
from random import random

class Server:
# basic s
    def __init__(self, fail_likelihood, processing_speed, cache=dict, processing_attempts = 0, server_id = None, online = True, requests_processed = 0):
        self.server_id = server_id
        if server_id == None:
            self.server_id = randomid()
        self.online = online
        self.cache = cache
        self.requests_processed = requests_processed
        self.processing_attempts = processing_attempts
        self.fail_likelihood = fail_likelihood
        self.processing_speed = processing_speed

    def bring_online(self):
        self.online = True
    
    def take_offline(self):
        self.online = False

    def can_process(self):
        return self.online

    def in_cache(self, endpoint):
        return endpoint in self.cache
    

    def process_request(self, request):
        if self.can_process() and not self.in_cache(request.endpoint):
            self.processing_attempts += 1
            if random() < self.fail_likelihood:
                request.retry()
            else:
                self.cache[request.endpoint]  
                request.mark_completed()
                self.requests_processed += 1
                self.processing_attempts += 1
        else:
            if self.can_process():
                request.mark_completed()
            else:
                pass
    
    def process_queue(self, queue):
        if queue.is_empty():
            pass
        else:
            request = queue.dequeue()
            self.process_request(request) 
            if request.status == "Completed" or request.status == "Failed":
                pass
            elif request.status == "Retrying":
                queue.enqueue(request)
            return self.process_queue(queue)
    








    
