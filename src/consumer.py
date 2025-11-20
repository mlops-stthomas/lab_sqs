import json
import time
import logging
import boto3
from handler import handle_message
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


def send_to_dlq(message_body: str, error_reason: str):
    """Send failed message to Dead Letter Queue if configured."""
    if not settings.DLQ_URL:
        logger.warning("No DLQ configured, discarding failed message")
        return

    try:
        dlq_payload = {
            "original_message": message_body,
            "error_reason": error_reason,
            "timestamp": time.time()
        }
        sqs.send_message(
            QueueUrl=settings.DLQ_URL,
            MessageBody=json.dumps(dlq_payload)
        )
        logger.info(f"Sent failed message to DLQ: {error_reason}")
    except Exception as e:
        logger.error(f"Failed to send message to DLQ: {e}")


def process_message(msg: dict) -> bool:
    """
    Process a single SQS message.
    Returns True if message was processed successfully, False otherwise.
    """
    receipt_handle = msg["ReceiptHandle"]
    message_id = msg.get("MessageId", "unknown")

    try:
        # Attempt to parse JSON
        body = json.loads(msg["Body"])
        logger.info(f"Processing message {message_id}")

        # Handle the message
        handle_message(body)

        # Delete message after successful processing
        sqs.delete_message(
            QueueUrl=settings.QUEUE_URL,
            ReceiptHandle=receipt_handle
        )
        logger.info(f"Successfully processed and deleted message {message_id}")
        return True

    except json.JSONDecodeError as e:
        # Non-JSON messages should be moved to DLQ or deleted
        logger.error(f"Invalid JSON in message {message_id}: {e}")
        send_to_dlq(msg["Body"], f"JSON decode error: {str(e)}")

        # Delete the invalid message to prevent reprocessing
        sqs.delete_message(
            QueueUrl=settings.QUEUE_URL,
            ReceiptHandle=receipt_handle
        )
        logger.warning(f"Deleted invalid message {message_id}")
        return False

    except Exception as e:
        # Other processing errors - message will return to queue
        logger.error(f"Error processing message {message_id}: {e}", exc_info=True)
        return False


def poll():
    """Main polling loop for SQS messages."""
    logger.info(f"Starting SQS consumer for queue: {settings.QUEUE_URL}")
    logger.info(f"Settings: MaxMessages={settings.MAX_MESSAGES}, "
                f"VisibilityTimeout={settings.VISIBILITY_TIMEOUT}s, "
                f"WaitTime={settings.WAIT_TIME}s")

    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=settings.QUEUE_URL,
                MaxNumberOfMessages=settings.MAX_MESSAGES,
                VisibilityTimeout=settings.VISIBILITY_TIMEOUT,
                WaitTimeSeconds=settings.WAIT_TIME,
                AttributeNames=["All"],
                MessageAttributeNames=["All"]
            )

            messages = response.get("Messages", [])
            if not messages:
                logger.debug("No messages received, continuing to poll...")
                continue

            logger.info(f"Received {len(messages)} message(s)")

            # Process each message
            for msg in messages:
                process_message(msg)

        except KeyboardInterrupt:
            logger.info("Consumer stopped by user")
            break

        except Exception as e:
            logger.error(f"Fatal poll error: {e}", exc_info=True)
            time.sleep(5)  # Backoff before retrying


if __name__ == "__main__":
    poll()
