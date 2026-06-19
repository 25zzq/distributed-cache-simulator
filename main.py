from src.request import Request
from src.requestqueue import RequestQueue as Queue
from src.server import Server
server = Server(0.8, 2)
requestorder = Queue()
def main():
    print("Distributed Cache Simulator starting...")
    testrequest = Request(
        endpoint="/get-user",
        payload={"dave": 123}, 
        max_retries=3, status="Sending")\

    testrequest2 = Request(
        endpoint="/add-user",
        payload={"john": 123}, 
        max_retries=3, status="Sending")
    
    testrequest3 = Request(
        endpoint="/unadd-user",
        payload={"john": 123}, 
        max_retries=3, status="Sending")
    
    testrequest4 = Request(
        endpoint="/unadd-user",
        payload={"john": 123}, 
        max_retries=3, status="Sending")
    
    testrequest5 = Request(
        endpoint="/unadd-user",
        payload={"john": 123}, 
        max_retries=3, status="Sending")
    
    testrequest6 = Request(
        endpoint="/unadd-user",
        payload={"john": 123}, 
        max_retries=3, status="Sending")
    
    testrequest7 = Request(
        endpoint="/unadd-user",
        payload={"john": 123}, 
        max_retries=3, status="Sending")
    
    testrequest8 = Request(
        endpoint="/unadd-user",
        payload={"john": 123}, 
        max_retries=3, status="Sending")
    
    testrequest9 = Request(
        endpoint="/unadd-user",
        payload={"john": 123}, 
        max_retries=3, status="Sending")
    
    testrequest10 = Request(
        endpoint="/unadd-user",
        payload={"john": 123}, 
        max_retries=3, status="Sending")
    
    testrequest11 = Request(
        endpoint="/unadd-user",
        payload={"john": 123}, 
        max_retries=3, status="Sending")
    
    
    

    
    #testing out the server's functionality
    requestorder.enqueue(testrequest)
    requestorder.enqueue(testrequest2)
    requestorder.enqueue(testrequest4)
    requestorder.enqueue(testrequest5)
    requestorder.enqueue(testrequest6)
    requestorder.enqueue(testrequest7)
    requestorder.enqueue(testrequest8)
    requestorder.enqueue(testrequest9)
    requestorder.enqueue(testrequest10)
    requestorder.enqueue(testrequest11)


    

    bigahhserver.process_queue(requestorder)

    
    print(bigahhserver.requests_processed)
    print(bigahhserver.processing_attempts)


if __name__ == "__main__":
    main()