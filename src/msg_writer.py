import json
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


def generate_custom_message(msg):
    return {"message": str(msg)}


def generate_invalid_message(msg):
    return "This is not json"


def run_writer(queue_url, msg, invalid=False):
    if invalid:
        message_body = generate_invalid_message(msg)
        logger.warning(f"Sending INVALID (non-JSON) message: {message_body}")
    else:
        message = generate_custom_message(msg)
        message_body = json.dumps(message)
        logger.info(f"Sending valid JSON message: {msg}")

    try:
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=message_body
        )
        logger.info(f"Message sent - MessageId: {response['MessageId']}")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--msg", type=str, default="MLOPS Rocks")
    parser.add_argument("--invalid", action="store_true",
                        help="Send invalid non-JSON message for testing")
    args = parser.parse_args()

    run_writer(settings.QUEUE_URL, args.msg, args.invalid)
