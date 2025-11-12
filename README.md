# lab_sqs

# SQS Consumer + Writer Setup Instructions

Follow these steps to install dependencies, run the SQS consumer, and generate messages to test queue depth.

---

## 1. Create and Activate a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate

## 2. Install Dependencies
Make sure you are in the same directory as requirements.txt:

```bash
pip install -r requirements.txt

## 3. Running the SQS Consumer

```bash
python consumer/main.py
