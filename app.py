from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse
from ultralytics import YOLO
from PIL import Image
import sqlite3
import os
import uuid
import shutil
from pydantic import BaseModel
from typing import Optional
from s3 import download_image_from_s3, upload_predicted_image_to_s3

import torch
torch.cuda.is_available = lambda: False

app = FastAPI()

UPLOAD_DIR = "uploads/original"
PREDICTED_DIR = "uploads/predicted"
DB_PATH = "predictions.db"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PREDICTED_DIR, exist_ok=True)

model = YOLO("yolov8n.pt")


class S3ImageRequest(BaseModel):
    chat_id: str
    image_name: str


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prediction_sessions (
                uid TEXT PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
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


init_db()


def save_prediction_session(uid, original_image, predicted_image):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO prediction_sessions (uid, original_image, predicted_image)
            VALUES (?, ?, ?)
        """, (uid, original_image, predicted_image))


def save_detection_object(prediction_uid, label, score, box):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO detection_objects (prediction_uid, label, score, box)
            VALUES (?, ?, ?, ?)
        """, (prediction_uid, label, score, str(box)))


@app.post("/predict")
async def predict(request: Request, file: Optional[UploadFile] = File(None)):
    uid = str(uuid.uuid4())
    ext = ".jpg"
    chat_id = image_name = None

    try:
        json_data = await request.json()
        if "image_name" in json_data and "chat_id" in json_data:
            image_name = json_data["image_name"]
            chat_id = json_data["chat_id"]
            ext = os.path.splitext(image_name)[1]
            original_tmp = f"/tmp/{uid}_original{ext}"
            predicted_tmp = f"/tmp/{uid}_predicted{ext}"
            download_image_from_s3(chat_id, image_name, original_tmp)
        else:
            raise ValueError
    except:
        if file is not None:
            ext = os.path.splitext(file.filename)[1]
            original_tmp = f"/tmp/{uid}{ext}"
            predicted_tmp = f"/tmp/{uid}_predicted{ext}"
            with open(original_tmp, "wb") as f:
                shutil.copyfileobj(file.file, f)
        else:
            raise HTTPException(status_code=400, detail="No image_name+chat_id or file provided")

    results = model(original_tmp, device="cpu")
    annotated = results[0].plot()
    Image.fromarray(annotated).save(predicted_tmp)

    # Final save locations
    original_final = os.path.join(UPLOAD_DIR, f"{uid}{ext}")
    predicted_final = os.path.join(PREDICTED_DIR, f"{uid}_predicted{ext}")
    shutil.copy(original_tmp, original_final)
    shutil.copy(predicted_tmp, predicted_final)

    if chat_id:
        upload_predicted_image_to_s3(chat_id, image_name, predicted_tmp)

    save_prediction_session(uid, original_final, predicted_final)

    for box in results[0].boxes:
        label_idx = int(box.cls[0].item())
        label = model.names[label_idx]
        score = float(box.conf[0])
        bbox = box.xyxy[0].tolist()
        save_detection_object(uid, label, score, bbox)

    try:
        os.remove(original_tmp)
        os.remove(predicted_tmp)
    except:
        pass

    return {
        "prediction_uid": uid,
        "detection_count": len(results[0].boxes),
        "labels": [model.names[int(box.cls[0])] for box in results[0].boxes]
    }


@app.get("/prediction/{uid}")
def get_prediction_by_uid(uid: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        session = conn.execute("SELECT * FROM prediction_sessions WHERE uid = ?", (uid,)).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Prediction not found")
        objects = conn.execute("SELECT * FROM detection_objects WHERE prediction_uid = ?", (uid,)).fetchall()
        return {
            "uid": session["uid"],
            "timestamp": session["timestamp"],
            "original_image": session["original_image"],
            "predicted_image": session["predicted_image"],
            "detection_objects": [
                {"id": o["id"], "label": o["label"], "score": o["score"], "box": o["box"]}
                for o in objects
            ]
        }


@app.get("/predictions/label/{label}")
def get_predictions_by_label(label: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT DISTINCT ps.uid, ps.timestamp
            FROM prediction_sessions ps
            JOIN detection_objects do ON ps.uid = do.prediction_uid
            WHERE do.label = ?
        """, (label,)).fetchall()
        return [{"uid": row["uid"], "timestamp": row["timestamp"]} for row in rows]


@app.get("/predictions/score/{min_score}")
def get_predictions_by_score(min_score: float):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT DISTINCT ps.uid, ps.timestamp
            FROM prediction_sessions ps
            JOIN detection_objects do ON ps.uid = do.prediction_uid
            WHERE do.score >= ?
        """, (min_score,)).fetchall()
        return [{"uid": row["uid"], "timestamp": row["timestamp"]} for row in rows]


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
    accept_header = request.headers.get("accept", "")

    try:
        with sqlite3.connect(DB_PATH) as conn:
            result = conn.execute(
                "SELECT predicted_image FROM prediction_sessions WHERE uid = ?",
                (uid,)
            ).fetchone()
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")

    if not result:
        raise HTTPException(status_code=404, detail="Prediction not found")

    image_path = result[0]

    if not os.path.exists(image_path):
        try:
            filename = os.path.basename(image_path)
            if "_" not in filename:
                raise ValueError("Invalid filename format for S3 fallback")
            chat_id = filename.split("_")[0]
            download_predicted_image_from_s3(chat_id, filename, image_path)
        except Exception as e:
            raise HTTPException(status_code=404, detail="Predicted image not found locally or on S3")

    if "image/png" in accept_header:
        return FileResponse(image_path, media_type="image/png")
    elif "image/jpeg" in accept_header or "image/jpg" in accept_header or "*/*" in accept_header:
        return FileResponse(image_path, media_type="image/jpeg")
    else:
        raise HTTPException(status_code=406, detail="Client does not accept an image format")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/hello")
def hello():
    return {"hello": "world"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
