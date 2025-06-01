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
