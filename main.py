from src.request import Request
from src.requestqueue import RequestQueue as Queue
from src.server import Server
bigahhserver = Server(0.0, 2)
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
    
    #testing out the server's functionality
    requestorder.enqueue(testrequest)
    requestorder.enqueue(testrequest2)
    requestorder.enqueue(testrequest3)

    print(testrequest.status)
    print(testrequest2.status)
    print(testrequest3.status)

    bigahhserver.process_queue(requestorder)

    

    print(testrequest.status)
    print(testrequest2.status)
    print(testrequest3.status)


if __name__ == "__main__":
    main()