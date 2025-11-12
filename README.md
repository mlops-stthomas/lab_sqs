# lab_sqs

# SQS Consumer + Writer Setup Instructions

Follow these steps to install dependencies, run the SQS consumer, and generate messages to test queue depth.

---

## 0. Navigate to AWS SQS and create a new queue.  
Create a standard queue with no encryption. 

Look at the URL of the queue.  You will need to set this in the settings for the lab. 

## 1. Create and Activate a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 2. Install Dependencies
Make sure you are in the same directory as requirements.txt:

```bash
pip install -r requirements.txt
```


## 3. Running the SQS Consumer

```bash
python consumer/consumer.py
```

In another terminal try running the writers. 

```bash
python writer.py --n 1000
```

```bash
python msg_writer.py --msg "This is my message"
```


## 4. Scenarios to try
1. Try sending thousands of messages.  Look at the logs and see the messages build up in the SQS dashboard

2. Try turning on the consumer after sending the messages

3. Look at the message order.  Are they in order?  Why or why not?

4. Try sending a message that isn't json.  What happens?

5.  How would messages that are not json get removed?  What should we do?

