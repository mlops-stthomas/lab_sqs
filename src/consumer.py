import json
import time
import boto3
from handler import handle_message
import settings

sqs = boto3.client("sqs")


def poll():
    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=settings.QUEUE_URL,
                MaxNumberOfMessages=settings.MAX_MESSAGES,
                VisibilityTimeout=settings.VISIBILITY_TIMEOUT,
                WaitTimeSeconds=settings.WAIT_TIME,
            )

            messages = response.get("Messages", [])
            if not messages:
                continue

            for msg in messages:
                receipt_handle = msg["ReceiptHandle"]

                try:
                    body = json.loads(msg["Body"])
                    handle_message(body)

                    sqs.delete_message(
                        QueueUrl=settings.QUEUE_URL, ReceiptHandle=receipt_handle
                    )

                except Exception as e:
                    print(f"Error processing message: {e}")

        except Exception as e:
            print("Fatal poll error:", e)
            time.sleep(5)  # backoff before retrying


if __name__ == "__main__":
    poll()
