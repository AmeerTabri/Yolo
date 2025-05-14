#!/bin/bash

cd ~/Yolo  # or /mnt/Yolo if you use that

# Step 1: Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

# Step 2: Activate venv and install dependencies
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Step 3: Copy the systemd service file
sudo cp yolo.service /etc/systemd/system/

# Step 4: Reload and restart the service
sudo systemctl daemon-reload
sudo systemctl restart yolo.service
sudo systemctl enable yolo.service

# Step 5: Check if service is active
if ! systemctl is-active --quiet yolo.service; then
  echo "❌ yolo.service is not running."
  sudo systemctl status yolo.service --no-pager
  exit 1
else
  echo "✅ yolo.service is running."
fi