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

# Disable GPU usage
import torch
torch.cuda.is_available = lambda: False

app = FastAPI()

UPLOAD_DIR = "uploads/original"
PREDICTED_DIR = "uploads/predicted"
DB_PATH = "predictions.db"
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "AmeerPredictions")
DYNAMODB_REGION = os.getenv("AWS_REGION", "us-west-2")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PREDICTED_DIR, exist_ok=True)

# Load YOLO model
model = YOLO("yolov8n.pt")

# === Storage Interface ===

class StorageInterface(ABC):
    @abstractmethod
    def save_prediction(self, prediction_id, chat_id, original_image, predicted_image):
        pass

    @abstractmethod
    def save_detection(self, prediction_id, label, score, box):
        pass

    @abstractmethod
    def get_prediction(self, prediction_id):
        pass

    @abstractmethod
    def get_predictions_by_label(self, label):
        pass

    @abstractmethod
    def get_predictions_by_score(self, min_score):
        pass

# === SQLite Storage ===

class SQLiteStorage(StorageInterface):
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prediction_sessions (
                    uid TEXT PRIMARY KEY,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    chat_id TEXT,
                    original_image TEXT,
                    predicted_image TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS detection_objects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prediction_uid TEXT,
                    label TEXT,
                    score REAL,
                    box TEXT,
                    FOREIGN KEY (prediction_uid) REFERENCES prediction_sessions (uid)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prediction_uid ON detection_objects (prediction_uid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_label ON detection_objects (label)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_score ON detection_objects (score)")

    def save_prediction(self, prediction_id, chat_id, original_image, predicted_image):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO prediction_sessions (uid, chat_id, original_image, predicted_image)
                VALUES (?, ?, ?, ?)
            """, (prediction_id, chat_id, original_image, predicted_image))

    def save_detection(self, prediction_id, label, score, box):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO detection_objects (prediction_uid, label, score, box)
                VALUES (?, ?, ?, ?)
            """, (prediction_id, label, score, str(box)))

    def get_prediction(self, prediction_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            session = conn.execute("SELECT * FROM prediction_sessions WHERE uid = ?", (prediction_id,)).fetchone()
            if not session:
                return None
            objects = conn.execute("SELECT * FROM detection_objects WHERE prediction_uid = ?", (prediction_id,)).fetchall()
            return {
                "uid": session["uid"],
                "chat_id": session["chat_id"],
                "timestamp": session["timestamp"],
                "original_image": session["original_image"],
                "predicted_image": session["predicted_image"],
                "detection_objects": [
                    {
                        "id": obj["id"],
                        "label": obj["label"],
                        "score": obj["score"],
                        "box": obj["box"]
                    } for obj in objects
                ]
            }

    def get_predictions_by_label(self, label):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT DISTINCT ps.uid, ps.timestamp
                FROM prediction_sessions ps
                JOIN detection_objects do ON ps.uid = do.prediction_uid
                WHERE do.label = ?
            """, (label,)).fetchall()
            return [{"uid": row["uid"], "timestamp": row["timestamp"]} for row in rows]

    def get_predictions_by_score(self, min_score):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT DISTINCT ps.uid, ps.timestamp
                FROM prediction_sessions ps
                JOIN detection_objects do ON ps.uid = do.prediction_uid
                WHERE do.score >= ?
            """, (min_score,)).fetchall()
            return [{"uid": row["uid"], "timestamp": row["timestamp"]} for row in rows]

# === DynamoDB Storage ===

class DynamoDBStorage(StorageInterface):
    def __init__(self, table_name):
        self.table = boto3.resource('dynamodb', region_name=DYNAMODB_REGION).Table(table_name)

    def save_prediction(self, prediction_id, chat_id, original_image, predicted_image):
        self.table.put_item(
            Item={
                'PredictionID': prediction_id,
                'ChatID': chat_id,
                'OriginalImagePath': original_image,
                'PredictedImagePath': predicted_image,
                'Detections': []
            }
        )

    def save_detection(self, prediction_id, label, score, box):
        self.table.update_item(
            Key={'PredictionID': prediction_id},
            UpdateExpression="SET Detections = list_append(if_not_exists(Detections, :empty), :det)",
            ExpressionAttributeValues={
                ':det': [{'Label': label, 'Score': Decimal(str(score)), 'Box': str(box)}],
                ':empty': []
            }
        )

    def get_prediction(self, prediction_id):
        response = self.table.get_item(Key={'PredictionID': prediction_id})
        item = response.get('Item')
        if not item:
            return None
        return {
            "uid": item["PredictionID"],
            "chat_id": item.get("ChatID"),
            "original_image": item.get("OriginalImagePath"),
            "predicted_image": item.get("PredictedImagePath"),
            "detection_objects": item.get("Detections", [])
        }

    def get_predictions_by_label(self, label):
        raise HTTPException(status_code=501, detail="DynamoDB: get by label requires GSI")

    def get_predictions_by_score(self, min_score):
        raise HTTPException(status_code=501, detail="DynamoDB: get by score requires GSI")

# === Storage selector ===

storage_type = os.getenv("STORAGE_TYPE", "dynamodb")
if storage_type == "dynamodb":
    storage = DynamoDBStorage(DYNAMODB_TABLE)
else:
    storage = SQLiteStorage(DB_PATH)

# === Routes ===

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

