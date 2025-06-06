#!/bin/bash

cd ~/Yolo  # or /mnt/Yolo if you use that

# Ensure Python + pip + venv are installed
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

# Step 1: Create virtual environment
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv || { echo "❌ Failed to create virtualenv"; exit 1; }
fi

# Step 1.5: Force install pip if missing (Ubuntu 24.04 bug workaround)
if [ ! -x ".venv/bin/pip" ]; then
  echo "⚠️ pip still not found, using get-pip.py workaround..."
  curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py
  ./.venv/bin/python get-pip.py
  rm get-pip.py
fi

# Step 2: Install dependencies directly using venv pip
echo "Installing dependencies..."
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

# Step 3: Copy the systemd service file
echo "Copying systemd service file..."
sudo cp yolo_dev.service /etc/systemd/system/

# Step 4: Reload and restart the service
echo "Restarting yolo_dev.service..."
sudo systemctl daemon-reload
sudo systemctl restart yolo_dev.service
sudo systemctl enable yolo_dev.service

# Step 5: Check if service is active
if ! systemctl is-active --quiet yolo_dev.service; then
  echo "❌ yolo_dev.service is not running."
  sudo systemctl status yolo_dev.service --no-pager
  exit 1
else
  echo "✅ yolo_dev.service is running."
fi
