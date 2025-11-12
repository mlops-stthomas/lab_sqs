import json
import time
import uuid
import boto3
import argparse
import settings

sqs = boto3.client("sqs")

def generate_custom_message(msg):
    return {
        "message": str(msg)
    }
    
def generate_invalid_message(msg):
    return "This is not json"


def run_writer(queue_url, msg):
    message = generate_custom_message(msg)
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(message)
    )

    print(f"Sent msg", msg)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--msg", type=str, default="MLOPS Rocks")
    args = parser.parse_args()

    run_writer(settings.QUEUE_URL, args.msg)