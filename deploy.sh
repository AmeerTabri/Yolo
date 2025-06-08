#!/bin/bash

cd ~/Yolo

# Step 0: Create .env.prod from environment variables
echo "Creating .env.prod..."
cat <<EOF > .env.prod
AWS_REGION=${AWS_REGION}
AWS_S3_BUCKET=${AWS_S3_BUCKET}
AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
EOF

# Ensure Python + pip + venv are installed
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

# Step 1: Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv || { echo "❌ Failed to create virtualenv"; exit 1; }
fi

# Step 1.5: Fix missing pip (Ubuntu 24.04 workaround)
if [ ! -x ".venv/bin/pip" ]; then
  echo "⚠️ pip not found in .venv, using get-pip.py workaround..."
  curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py
  .venv/bin/python get-pip.py
  rm get-pip.py
fi

# Step 2: Install dependencies
echo "Installing dependencies..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Step 3: Copy the systemd service file
echo "Copying yolo.service to /etc/systemd/system..."
sudo cp yolo.service /etc/systemd/system/

# Step 4: Reload and restart the service
echo "Restarting yolo.service..."
sudo systemctl daemon-reload
sudo systemctl restart yolo.service
sudo systemctl enable yolo.service

# Step 5: Verify service is running
if ! systemctl is-active --quiet yolo.service; then
  echo "❌ yolo.service is not running."
  sudo systemctl status yolo.service --no-pager
  exit 1
else
  echo "✅ yolo.service is running."
fi
