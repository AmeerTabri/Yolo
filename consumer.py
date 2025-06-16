import boto3
import os
import json
import time
import uuid
import requests
from ultralytics import YOLO
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

from s3 import download_image_from_s3, upload_predicted_image_to_s3

# === Config ===
SQS_REGION = os.getenv("SQS_AWS_REGION")
QUEUE_URL = os.getenv("QUEUE_URL")
POLYBOT_URL = os.getenv("POLYBOT_URL")  # e.g. https://<ngrok-id>.ngrok-free.app

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
            # === Download original image ===
            download_image_from_s3(chat_id, image_name, original_path)

            # === Run YOLO ===
            results = model(original_path, device="cpu")
            annotated = results[0].plot()
            Image.fromarray(annotated).save(predicted_path)

            # === Upload predicted image ===
            upload_predicted_image_to_s3(chat_id, image_name, predicted_path)

            # === Create labels list ===
            labels = [model.names[int(box.cls[0].item())] for box in results[0].boxes]

            # === Send callback request to Polybot ===
            callback_payload = {
                "chat_id": chat_id,
                "labels": labels,
                "image_name": image_name
            }

            response = requests.post(f"{POLYBOT_URL}/yolo_callback", json=callback_payload)
            print(f"✅ Callback sent to Polybot: {response.status_code}")

            print(f"✅ Processed and uploaded: {chat_id}/predicted/{image_name}")

        except Exception as e:
            print(f"❌ Error processing message: {e}")

        finally:
            # Clean up local files
            for p in [original_path, predicted_path]:
                try: os.remove(p)
                except: pass

            # Delete the SQS message
            sqs.delete_message(
                QueueUrl=QUEUE_URL,
                ReceiptHandle=msg['ReceiptHandle']
            )
