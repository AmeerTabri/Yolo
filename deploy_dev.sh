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

# --- Step 6: Install OpenTelemetry Collector ---
if ! command -v otelcol &> /dev/null; then
  echo "Installing OpenTelemetry Collector..."
  sudo apt-get update
  sudo apt-get -y install wget
  wget https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.127.0/otelcol_0.127.0_linux_amd64.deb
  sudo dpkg -i otelcol_0.127.0_linux_amd64.deb
  rm otelcol_0.127.0_linux_amd64.deb
else
  echo "✅ OpenTelemetry Collector already installed."
fi

# --- Step 7: Configure OpenTelemetry Collector ---
echo "Configuring OpenTelemetry Collector..."
sudo mkdir -p /etc/otelcol
sudo tee /etc/otelcol/config.yaml > /dev/null <<EOF
receivers:
  hostmetrics:
    collection_interval: 15s
    scrapers:
      cpu:
      memory:
      disk:
      filesystem:
      load:
      network:
      processes:

exporters:
  prometheus:
    endpoint: "0.0.0.0:8889"

service:
  pipelines:
    metrics:
      receivers: [hostmetrics]
      exporters: [prometheus]
EOF

# --- Step 8: Restart and enable otelcol ---
sudo systemctl restart otelcol
sudo systemctl enable otelcol

# --- Step 9: Verify otelcol is running ---
if ! systemctl is-active --quiet otelcol; then
  echo "❌ otelcol service is not running."
  sudo systemctl status otelcol --no-pager
  exit 1
else
  echo "✅ otelcol service is running and exposing metrics on port 8889."
fi