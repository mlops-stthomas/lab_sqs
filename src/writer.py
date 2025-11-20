import json
import time
import uuid
import logging
import boto3
import argparse
import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize SQS client with credentials
sqs = boto3.client(
    "sqs",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
)


def generate_payload(message_num):
    """
    Creates roughly size_bytes of JSON payload.
    """
    return {"id": str(uuid.uuid4()), "payload": str(message_num)}


def run_writer(queue_url, n, delay):
    logger.info(f"Starting to send {n} messages to {queue_url}")
    start_time = time.time()

    for i in range(n):
        msg = generate_payload(i)

        try:
            response = sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(msg)
            )
            logger.info(f"Sent {i+1}/{n} - MessageId: {response['MessageId']}")
        except Exception as e:
            logger.error(f"Failed to send message {i+1}/{n}: {e}")

        if delay > 0:
            time.sleep(delay)

    elapsed = time.time() - start_time
    logger.info(f"Completed sending {n} messages in {elapsed:.2f} seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--delay", type=float, default=0.0)
    args = parser.parse_args()

    run_writer(settings.QUEUE_URL, args.n, args.delay)
