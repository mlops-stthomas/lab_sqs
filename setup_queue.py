"""
Setup script to create SQS queues and update .env file
"""
import boto3
import os
from dotenv import load_dotenv

# Load current environment
load_dotenv()

# Initialize SQS client
sqs = boto3.client(
    'sqs',
    region_name=os.getenv('AWS_REGION', 'us-east-2'),
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)

def create_queue(queue_name: str, is_dlq: bool = False):
    """Create an SQS queue and return its URL."""
    try:
        print(f"Creating queue: {queue_name}...")
        response = sqs.create_queue(
            QueueName=queue_name,
            Attributes={
                'ReceiveMessageWaitTimeSeconds': '20',  # Long polling
                'VisibilityTimeout': '30'
            }
        )
        queue_url = response['QueueUrl']
        print(f"✓ Queue created: {queue_url}")
        return queue_url
    except sqs.exceptions.QueueNameExists:
        print(f"Queue {queue_name} already exists, getting URL...")
        response = sqs.get_queue_url(QueueName=queue_name)
        queue_url = response['QueueUrl']
        print(f"✓ Queue URL: {queue_url}")
        return queue_url
    except Exception as e:
        print(f"✗ Error creating queue: {e}")
        return None

def update_env_file(queue_url: str, dlq_url: str = None):
    """Update .env file with queue URLs."""
    try:
        with open('.env', 'r') as f:
            lines = f.readlines()

        with open('.env', 'w') as f:
            for line in lines:
                if line.startswith('QUEUE_URL='):
                    f.write(f'QUEUE_URL={queue_url}\n')
                elif line.startswith('DLQ_URL=') and dlq_url:
                    f.write(f'DLQ_URL={dlq_url}\n')
                else:
                    f.write(line)

        print(f"✓ Updated .env file")
        print(f"  QUEUE_URL={queue_url}")
        if dlq_url:
            print(f"  DLQ_URL={dlq_url}")
    except Exception as e:
        print(f"✗ Error updating .env file: {e}")

def main():
    print("=" * 60)
    print("SQS Queue Setup")
    print("=" * 60)

    # Create main queue
    queue_name = "lab-sqs-queue"
    queue_url = create_queue(queue_name)

    if not queue_url:
        print("\n✗ Failed to create main queue. Exiting.")
        return

    # Create DLQ automatically
    print("\nCreating Dead Letter Queue (DLQ)...")
    dlq_name = "lab-sqs-dlq"
    dlq_url = create_queue(dlq_name, is_dlq=True)

    # Update .env file
    print("\nUpdating .env file...")
    update_env_file(queue_url, dlq_url)

    print("\n" + "=" * 60)
    print("✓ Setup complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Run the consumer: python src/consumer.py")
    print("2. Send a test message: python src/msg_writer.py --msg 'Hello!'")
    print("\nHappy testing!")

if __name__ == "__main__":
    main()
