# SQS message ordering

## Standard queues vs FIFO queues

### Standard queues (current setup)
- **Ordering**: Best-effort ordering, messages may arrive out of order
- **Throughput**: Nearly unlimited transactions per second
- **Delivery**: At-least-once delivery (messages may be delivered more than once)
- **Use case**: High throughput scenarios where order doesn't matter

### FIFO queues
- **Ordering**: Strict message ordering (first-in, first-out)
- **Throughput**: 300 messages per second (or 3000 with batching)
- **Delivery**: Exactly-once processing
- **Use case**: When message order is critical
- **Queue name**: Must end with `.fifo` suffix

## Why messages are out of order

Standard SQS queues use a distributed architecture with multiple servers. When you send messages:

1. Messages are distributed across multiple servers for redundancy
2. Each consumer polls from potentially different servers
3. Network latency varies between servers
4. Messages may be delivered multiple times if not deleted quickly

Example scenario:
```
Send: Message 1, 2, 3, 4, 5
Receive: Message 2, 1, 4, 5, 3  ← Out of order!
```

## Testing message ordering

### Test with standard queue
```bash
# Send 1000 messages
python src/writer.py --n 1000

# Run consumer and observe the order in logs
python src/consumer.py
```

You'll notice:
- Messages don't arrive in sequential order
- The "payload" field (message number) is not sequential
- This is expected behavior for standard queues

### Converting to FIFO queue

1. Create a new FIFO queue in AWS:
   - Queue name must end with `.fifo` (e.g., `lab-queue.fifo`)
   - Enable Content-Based Deduplication or use MessageDeduplicationId

2. Update `.env`:
   ```bash
   QUEUE_URL=https://sqs.us-east-2.amazonaws.com/084823914058/lab-queue.fifo
   ```

3. Modify writer to include MessageGroupId:
   ```python
   sqs.send_message(
       QueueUrl=queue_url,
       MessageBody=json.dumps(msg),
       MessageGroupId="lab-group-1",  # Required for FIFO
       MessageDeduplicationId=str(uuid.uuid4())  # If deduplication disabled
   )
   ```

## Message deduplication

### Content-based deduplication (recommended)
Enable this in the AWS Console for your FIFO queue. SQS will automatically deduplicate messages with identical content within a 5-minute window.

### Manual deduplication
If content-based deduplication is disabled, you must provide a `MessageDeduplicationId`:

```python
import hashlib

def generate_dedup_id(message_content):
    return hashlib.sha256(
        json.dumps(message_content, sort_keys=True).encode()
    ).hexdigest()
```

## Best practices

1. **Standard queues**: Use when you need high throughput and can tolerate:
   - Out-of-order delivery
   - Duplicate messages
   - At-least-once processing

2. **FIFO queues**: Use when you need:
   - Strict ordering within a message group
   - Exactly-once processing
   - Message deduplication

3. **Idempotency**: Always design message handlers to be idempotent (safe to process multiple times), even with FIFO queues

4. **Message groups**: In FIFO queues, use different MessageGroupIds to parallelize processing while maintaining order within each group
