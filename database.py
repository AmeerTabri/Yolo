import sqlite3
import boto3
import os
from abc import ABC, abstractmethod
from decimal import Decimal
from fastapi import HTTPException

# === Config ===
DYNAMODB_REGION = os.getenv("AWS_REGION", "us-west-2")

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
