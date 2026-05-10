from src.request import Request

def main():
    print("Distributed Cache Simulator starting...")
    testrequest = Request(
        endpoint="/get-user",
        payload={"dave": 123}, 
        max_retries=3, status="Sending")
    
    print(testrequest.status)

    testrequest.retry()

    print(testrequest.status)
    print(testrequest.retry_count)

    testrequest.mark_completed()

    print(testrequest.status)


if __name__ == "__main__":
    main()