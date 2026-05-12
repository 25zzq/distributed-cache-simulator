from src.request import Request
from src.requestqueue import RequestQueue

requestorder = RequestQueue()
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
    
    requestorder.enqueue(testrequest)
    print(requestorder.requests)
    requestorder.enqueue(testrequest2)
    print(requestorder.requests)
    requestorder.enqueue(testrequest3)
    print(requestorder.requests)

    removed_Request = requestorder.dequeue()
    print(f'{removed_Request.endpoint}')
    







    testrequest.retry()

    print(testrequest.status)
    print(testrequest.retry_count)

    testrequest.mark_completed()

    print(testrequest.status)


if __name__ == "__main__":
    main()