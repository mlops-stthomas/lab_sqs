def handle_message(msg_body: dict):
    """
    Actual application logic for a single message.
    """
    print(f"Handling message: {msg_body}")

    if msg_body.get("type") == "ping":
        print("Received ping")
