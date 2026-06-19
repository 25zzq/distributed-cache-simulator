class RequestQueue():
#queue data structure, easy implementation used with a regular array not a singly or doubly linked list
    def __init__(self):
        self.requests = []
    

    def enqueue(self, request):
        ## adds item to a queue
        self.requests.append(request) #O(1) complexity
        request.status = "Processing..."

        

    def dequeue(self):
        #removes item from the queue(either request timed out or request successfully processed)
        return self.requests.pop(0)  #O(n) Complexity

    def is_empty(self):
        return len(self.requests) == 0
    
        