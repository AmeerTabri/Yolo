FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
COPY torch-requirements.txt .

# Fix OpenCV + threading dependencies
RUN apt-get update && apt-get install -y libgl1 libglib2.0-0

RUN pip install-r requirements.txt && pip install -r torch-requirements.txt

COPY . .

CMD ["python", "app.py"]
