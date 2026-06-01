from uuid import uuid4 as randomid


class Server:
# basic s
    def __init__(self, fail_likelihood, processing_speed, server_id = None, online = True, requests_processed = 0):
        self.server_id = server_id
        if server_id == None:
            self.server_id = randomid()
        self.online = online
        self.requests_processed = requests_processed
        self.fail_likelihood = fail_likelihood
        self.processing_speed = processing_speed

    def bring_online(self):
        self.online = True
    
    def take_offline(self):
        self.online = False

    def can_process(self):
        return self.online

    def process_request(self, request):
        if self.can_process():
            request.mark_completed()
            self.requests_processed += 1
        else:
            pass
    
    def process_queue(self, queue):
        if queue.is_empty():
            pass
        else:
            self.process_request(queue.requests[0])
            queue.dequeue()
            return self.process_queue(queue)




    
