from uuid import uuid4

class Request():

    def __init__(self, endpoint, payload, max_retries, status, processing_time_ms = 120, retry_count = 0, request_id = None):
        self.request_id = request_id
        if self.request_id == None:
            self.request_id = uuid4()
        self.endpoint = endpoint
        self.payload = payload
        self.max_retries = max_retries
        self.status = status
        self.processing_time_ms = processing_time_ms
        self.retry_count = retry_count
    
    # retry will recursively call can_retry until max retries are met
    def can_retry(self):
        #checks if a request has exceeded it's retry count and creates a boolean that will be used for the retry function
        if self.retry_count >= self.max_retries:
            return False
        else:
            return True
    
    def retry(self):
        #uses the returned boolean value from can_retry to determine what happens next with a request in retrial stage
        if self.can_retry():
            #checks boolean value and increments the retry count until the max retries is met
            self.retry_count += 1
            self.status = "Retrying"
        else:
            self.status = "Failed"
        
    def mark_completed(self):
        self.status = "completed"
    

