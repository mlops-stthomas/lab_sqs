"""Quick test of consumer - processes one batch then exits"""
import json
import logging
import boto3
from src.handler import handle_message
from src import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

sqs = boto3.client(
    "sqs",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
)

def test_consumer():
    logger.info(f"Testing consumer with queue: {settings.QUEUE_URL}")

    response = sqs.receive_message(
        QueueUrl=settings.QUEUE_URL,
        MaxNumberOfMessages=settings.MAX_MESSAGES,
        WaitTimeSeconds=5
    )

    messages = response.get("Messages", [])
    logger.info(f"Received {len(messages)} message(s)")

    for msg in messages:
        try:
            body = json.loads(msg["Body"])
            logger.info(f"Processing: {body}")
            handle_message(body)

            # Delete message
            sqs.delete_message(
                QueueUrl=settings.QUEUE_URL,
                ReceiptHandle=msg["ReceiptHandle"]
            )
            logger.info(f"✓ Successfully processed and deleted message")
        except Exception as e:
            logger.error(f"Error: {e}")

    logger.info("Test complete!")

if __name__ == "__main__":
    test_consumer()
