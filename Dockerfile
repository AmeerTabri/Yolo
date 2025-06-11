FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
COPY torch-requirements.txt .

# Fix OpenCV dependency
RUN apt-get update && apt-get install -y libgl1

RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -r torch-requirements.txt

COPY . .

CMD ["python", "app.py"]
