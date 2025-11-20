import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# AWS Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")

# SQS Queue URLs
QUEUE_URL = os.getenv("QUEUE_URL")
DLQ_URL = os.getenv("DLQ_URL")

# Consumer Settings
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "10"))
VISIBILITY_TIMEOUT = int(os.getenv("VISIBILITY_TIMEOUT", "30"))
WAIT_TIME = int(os.getenv("WAIT_TIME", "20"))

# Validation
if not QUEUE_URL:
    raise ValueError("QUEUE_URL must be set in .env file")
if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
    raise ValueError("AWS credentials must be set in .env file")
