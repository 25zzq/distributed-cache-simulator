class RequestQueue():
#queue data structure, easy implementation used with a regular array not a singly or doubly linked list
    def __init__(self):
        self.requests = []
    

    def enqueue(self, request):
        ## adds item to a queue
        self.requests.append(request)

        

    def dequeue(self):
        #removes item from the queue(either request timed out or request successfully processed)
        return self.requests.pop(0)

        