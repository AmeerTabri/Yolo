from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form
from fastapi.responses import FileResponse
from ultralytics import YOLO
from PIL import Image
from abc import ABC, abstractmethod
from decimal import Decimal
import sqlite3
import boto3
import os
import uuid
import shutil
from typing import Optional
from s3 import download_image_from_s3, upload_predicted_image_to_s3
from database import SQLiteStorage, DynamoDBStorage

# Disable GPU usage
import torch
torch.cuda.is_available = lambda: False

app = FastAPI()

UPLOAD_DIR = "uploads/original"
PREDICTED_DIR = "uploads/predicted"
DB_PATH = "predictions.db"
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "AmeerPredictionsDev")
DYNAMODB_REGION = os.getenv("AWS_REGION", "us-west-2")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PREDICTED_DIR, exist_ok=True)

# Load YOLO model
model = YOLO("yolov8n.pt")

# Storage selector
storage_type = os.getenv("STORAGE_TYPE", "dynamodb")
if storage_type == "dynamodb":
    storage = DynamoDBStorage(DYNAMODB_TABLE)
else:
    storage = SQLiteStorage(DB_PATH)

@app.post("/predict")
async def predict(request: Request, file: Optional[UploadFile] = File(None), chat_id: Optional[str] = Form(None), image_id: Optional[str] = Form(None)):
    uid = str(uuid.uuid4())
    ext = ".jpg"
    image_name = None

    try:
        json_data = await request.json()
        if "image_name" in json_data and "chat_id" in json_data:
            image_name = json_data["image_name"]
            chat_id = json_data["chat_id"]

            original_path = f"/tmp/{uid}_original_{image_name}"
            predicted_path = f"/tmp/{uid}_predicted_{image_name}"

            download_image_from_s3(chat_id, image_name, original_path)
            ext = os.path.splitext(image_name)[1]
        else:
            raise ValueError
    except:
        if file is not None:
            ext = os.path.splitext(file.filename)[1]
            image_name = f"{uid}{ext}"  # ✅ make sure to define image_name for file uploads too
            original_path = os.path.join("/tmp", image_name)
            predicted_path = os.path.join("/tmp", f"predicted_{image_name}")
            with open(original_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
        else:
            raise HTTPException(status_code=400, detail="No image_name+chat_id or file provided")

    # ✅ Now define S3 keys AFTER both branches, guaranteed to work:
    s3_original_key = f"{chat_id}/original/image_{image_id}.jpg"
    s3_predicted_key = f"{chat_id}/predicted/image_{image_id}.jpg"

    results = model(original_path, device="cpu")
    annotated_frame = results[0].plot()
    annotated_image = Image.fromarray(annotated_frame)
    annotated_image.save(predicted_path)

    if chat_id:
        upload_predicted_image_to_s3(chat_id, image_id, predicted_path)

    storage.save_prediction(uid, chat_id, s3_original_key, s3_predicted_key)

    detected_labels = []
    for box in results[0].boxes:
        label_idx = int(box.cls[0].item())
        label = model.names[label_idx]
        score = float(box.conf[0])
        bbox = box.xyxy[0].tolist()
        storage.save_detection(uid, label, score, bbox)
        detected_labels.append(label)

    try:
        os.remove(original_path)
        os.remove(predicted_path)
    except Exception as e:
        print(f"Cleanup failed: {e}")

    return {
        "prediction_uid": uid,
        "detection_count": len(results[0].boxes),
        "labels": detected_labels
    }

@app.get("/prediction/{uid}")
def get_prediction_by_uid(uid: str):
    result = storage.get_prediction(uid)
    if not result:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return result

@app.get("/predictions/label/{label}")
def get_predictions_by_label(label: str):
    return storage.get_predictions_by_label(label)

@app.get("/predictions/score/{min_score}")
def get_predictions_by_score(min_score: float):
    return storage.get_predictions_by_score(min_score)

@app.get("/image/{type}/{filename}")
def get_image(type: str, filename: str):
    if type not in ["original", "predicted"]:
        raise HTTPException(status_code=400, detail="Invalid image type")
    path = os.path.join("uploads", type, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)

@app.get("/prediction/{uid}/image")
def get_prediction_image(uid: str, request: Request):
    accept = request.headers.get("accept", "")
    result = storage.get_prediction(uid)
    if not result:
        raise HTTPException(status_code=404, detail="Prediction not found")
    image_path = result.get("predicted_image")
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Predicted image file not found")
    if "image/png" in accept:
        return FileResponse(image_path, media_type="image/png")
    elif "image/jpeg" in accept or "image/jpg" in accept:
        return FileResponse(image_path, media_type="image/jpeg")
    else:
        raise HTTPException(status_code=406, detail="Client does not accept an image format")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/hello")
def hello():
    return {"hello world"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

