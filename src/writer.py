import json
import time
import uuid
import boto3
import argparse
import settings

sqs = boto3.client("sqs")


def generate_payload(message_num):
    """
    Creates roughly size_bytes of JSON payload.
    """
    return {"id": str(uuid.uuid4()), "payload": str(message_num)}


def run_writer(queue_url, n, delay):
    for i in range(n):
        msg = generate_payload(i)

        sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(msg))

        print(f"Sent {i+1}/{n}")
        if delay > 0:
            time.sleep(delay)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--delay", type=float, default=0.0)
    args = parser.parse_args()

    run_writer(settings.QUEUE_URL, args.n, args.delay)
