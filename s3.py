import boto3
from dotenv import load_dotenv

load_dotenv()

import os

AWS_REGION = os.getenv("AWS_REGION")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")

s3 = boto3.client("s3", region_name=AWS_REGION)

def download_image_from_s3(chat_id: str, image_id: str, local_path: str):
    s3_key = f"{chat_id}/original/image_{image_id}.jpg"
    s3.download_file(AWS_S3_BUCKET, s3_key, local_path)

def upload_predicted_image_to_s3(chat_id: str, image_id: str, local_path: str):
    s3_key = f"{chat_id}/predicted/image_{image_id}.jpg"
    s3.upload_file(local_path, AWS_S3_BUCKET, s3_key)
