import boto3
import os
import json
import time
import uuid
from ultralytics import YOLO
from PIL import Image

from dotenv import load_dotenv
load_dotenv()

# === Import your S3 helpers ===
from s3 import download_image_from_s3, upload_predicted_image_to_s3

# === SQS config ===
SQS_REGION = os.getenv("SQS_AWS_REGION")
QUEUE_URL = os.getenv("QUEUE_URL")

sqs = boto3.client('sqs', region_name=SQS_REGION)

# === Load YOLO model ===
model = YOLO("yolov8n.pt")  # Replace with your trained model if needed

while True:
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
        image_name = body['image_name']
        chat_id = body['chat_id']

        uid = str(uuid.uuid4())
        original_path = f"/tmp/{uid}_original_{image_name}"
        predicted_path = f"/tmp/{uid}_predicted_{image_name}"

        try:
            # ✅ Use your s3.py helpers
            download_image_from_s3(chat_id, image_name, original_path)

            results = model(original_path, device="cpu")
            annotated = results[0].plot()
            Image.fromarray(annotated).save(predicted_path)

            upload_predicted_image_to_s3(chat_id, image_name, predicted_path)

            print(f"✅ Processed and uploaded: {chat_id}/predicted/{image_name}")

        except Exception as e:
            print(f"❌ Error processing message: {e}")

        finally:
            for p in [original_path, predicted_path]:
                try: os.remove(p)
                except: pass

            sqs.delete_message(
                QueueUrl=QUEUE_URL,
                ReceiptHandle=msg['ReceiptHandle']
            )
