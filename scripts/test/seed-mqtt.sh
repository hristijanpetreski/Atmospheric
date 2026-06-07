#!/usr/bin/env bash
# scripts/test/seed-mqtt.sh
#
# Publishes randomly generated sensor readings to the MQTT broker
# for testing the ingestion pipeline (Telegraf → InfluxDB → Grafana).
#
# Usage:
#   bash scripts/test/seed-mqtt.sh [count] [delay]
#
# Arguments:
#   count   Number of messages to send (default: 20)
#   delay   Delay in seconds between messages (default: 0.5)
#
# Requirements:
#   mosquitto_pub (brew install mosquitto / pacman -S mosquitto)
#
# Example:
#   bash scripts/test/seed-mqtt.sh
#   bash scripts/test/seed-mqtt.sh 50 1

set -euo pipefail

HOST="${MQTT_HOST:-localhost}"
PORT="${MQTT_PORT:-1883}"
TOPIC="${MQTT_TOPIC:-atmospheric/sensors/esp32-test}"
COUNT="${1:-20}"
DELAY="${2:-0.5}"

if ! command -v mosquitto_pub &>/dev/null; then
  echo "Error: mosquitto_pub not found. Install with:"
  echo "  macOS:  brew install mosquitto"
  echo "  Arch:   sudo pacman -S mosquitto"
  echo "  Debian: sudo apt install mosquitto-clients"
  exit 1
fi

echo "Publishing $COUNT messages to $TOPIC every ${DELAY}s..."
echo ""

for i in $(seq 1 "$COUNT"); do
  temperature=$(awk "BEGIN {srand($RANDOM); printf \"%.2f\", 18 + rand() * 10}")
  humidity=$(awk "BEGIN {srand($RANDOM); printf \"%.2f\",  40 + rand() * 40}")
  pressure=$(awk "BEGIN {srand($RANDOM); printf \"%.2f\", 1008 + rand() * 10}")

  payload="{\"temperature\": $temperature, \"humidity\": $humidity, \"pressure\": $pressure}"

  mosquitto_pub -h "$HOST" -p "$PORT" -t "$TOPIC" -m "$payload"

  echo "[$i/$COUNT] $payload"
  sleep "$DELAY"
done

echo ""
echo "Done."
