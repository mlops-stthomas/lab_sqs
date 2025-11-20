# Quick setup guide

## Step-by-step setup

### 1. Create your SQS queue

1. Go to [AWS SQS Console](https://console.aws.amazon.com/sqs/v3/home?region=us-east-2)
2. Click "Create queue"
3. Queue type: **Standard** (or FIFO if you need ordering)
4. Name: Choose a name (e.g., `lab-sqs-queue`)
5. Leave other settings as default
6. Click "Create queue"
7. **Copy the queue URL** from the queue details page

### 2. Update .env file

Edit [.env](.env) and replace `YOUR_QUEUE_NAME` with your actual queue name:

```bash
QUEUE_URL=https://sqs.us-east-2.amazonaws.com/084823914058/lab-sqs-queue
```

### 3. Install dependencies

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 4. Verify setup

Check that your configuration is correct:

```bash
python -c "import src.settings; print('Queue URL:', src.settings.QUEUE_URL)"
```

You should see your queue URL printed without errors.

### 5. Run your first test

Terminal 1 - Start consumer:

```bash
python src/consumer.py
```

Terminal 2 - Send a test message:

```bash
python src/msg_writer.py --msg "Hello from SQS!"
```

You should see the consumer pick up and process the message!

## Optional: Create a Dead Letter Queue

1. Create another queue named `lab-sqs-dlq`
2. Add the DLQ URL to [.env](.env):

```bash
DLQ_URL=https://sqs.us-east-2.amazonaws.com/084823914058/lab-sqs-dlq
```

3. Test with an invalid message:

```bash
python src/msg_writer.py --msg "Test" --invalid
```

The invalid message should appear in your DLQ!

## Troubleshooting

### "QUEUE_URL must be set in .env file"

Make sure you updated the `.env` file with your actual queue name.

### "botocore.exceptions.NoCredentialsError"

Your AWS credentials in `.env` may be incorrect. Verify they're valid in AWS IAM Console.

### "Access Denied" errors

Your AWS IAM user needs these permissions:

- `sqs:SendMessage`
- `sqs:ReceiveMessage`
- `sqs:DeleteMessage`
- `sqs:GetQueueAttributes`

## Next steps

Once everything works:

1. Try the scenarios in [README.md](README.md)
2. Read about message ordering in [MESSAGE_ORDERING.md](MESSAGE_ORDERING.md)
3. Experiment with different consumer settings in [.env](.env)
