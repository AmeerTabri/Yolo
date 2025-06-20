import boto3
import os
import json
import time
import uuid
import requests
from dotenv import load_dotenv
from s3 import download_image_from_s3

load_dotenv()

# === Config ===
SQS_REGION = os.getenv("SQS_AWS_REGION")
QUEUE_URL = os.getenv("QUEUE_URL")
POLYBOT_URL = os.getenv("POLYBOT_URL")
YOLO_API_URL = "http://localhost:8080"

sqs = boto3.client('sqs', region_name=SQS_REGION)

print("✅ YOLO Consumer started. Listening for messages...")

while True:
    # === Receive message ===
    response = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=10
    )

    messages = response.get('Messages', [])
    if not messages:
        time.sleep(1)
        continue

    for msg in messages:
        body = json.loads(msg['Body'])
        image_id = body['image_id']
        chat_id = body['chat_id']

        uid = str(uuid.uuid4())
        original_path = f"/tmp/{uid}_original_{image_id}.jpg"

        try:
            # === Download image from S3 ===
            download_image_from_s3(chat_id, image_id, original_path)

            # === Call YOLO FastAPI `/predict` with file + chat_id ===
            with open(original_path, "rb") as f:
                print("files = ", f)
                predict_response = requests.post(
                    f"{YOLO_API_URL}/predict",
                    files={"file": f},
                    data={"chat_id": chat_id, "image_id": image_id}
                )
            predict_response.raise_for_status()
            predict_data = predict_response.json()

            labels = predict_data.get("labels", [])

            # === Send callback to Polybot ===
            callback_payload = {
                "chat_id": chat_id,
                "labels": labels,
                "image_id": image_id
            }
            callback_response = requests.post(
                f"{POLYBOT_URL}/yolo_callback",
                json=callback_payload
            )
            print(f"✅ Callback sent to Polybot: {callback_response.status_code}")

            print(f"✅ Processed: {chat_id}/{image_id} Labels: {labels}")

        except Exception as e:
            print(f"❌ Error processing message: {e}")

        finally:
            # === Cleanup ===
            try:
                os.remove(original_path)
            except:
                pass

            # === Delete message ===
            sqs.delete_message(
                QueueUrl=QUEUE_URL,
                ReceiptHandle=msg['ReceiptHandle']
            )
