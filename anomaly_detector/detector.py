import os
import sys
import json
import time
from collections import deque
import numpy as np
import pandas as pd
import paho.mqtt.client as mqtt
from sklearn.ensemble import IsolationForest

# Configuration from environment variables
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_USER = os.environ.get("MQTT_USER", None)
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", None)
INPUT_TOPIC = os.environ.get("INPUT_TOPIC", "atmospheric/sensors/+")
OUTPUT_TOPIC_PREFIX = os.environ.get("OUTPUT_TOPIC_PREFIX", "atmospheric/anomalies/")
WINDOW_SIZE = int(os.environ.get("WINDOW_SIZE", 1000))
MIN_SAMPLES = int(os.environ.get("MIN_SAMPLES", 30))
CONTAMINATION = float(os.environ.get("CONTAMINATION", 0.05))

# Device data buffers
# Dict mapping device_id -> deque of readings (dicts)
device_buffers = {}

def get_device_id(topic):
    # Topic format: atmospheric/sensors/{device_id}
    parts = topic.split('/')
    if len(parts) >= 3:
        return parts[2]
    return "unknown"

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(INPUT_TOPIC)
        print(f"Subscribed to topic: {INPUT_TOPIC}")
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
    except Exception as e:
        print(f"Error parsing JSON payload on {msg.topic}: {e}")
        return

    device_id = get_device_id(msg.topic)
    
    # Extract only numeric fields (temperature, humidity, pressure, etc.)
    numeric_reading = {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
    
    if not numeric_reading:
        print(f"No numeric fields found in message from {device_id}: {data}")
        return

    # Add timestamp if not present
    if "timestamp" not in numeric_reading:
        numeric_reading["timestamp"] = time.time()

    # Get or create the device buffer
    if device_id not in device_buffers:
        device_buffers[device_id] = deque(maxlen=WINDOW_SIZE)
    
    buffer = device_buffers[device_id]
    buffer.append(numeric_reading)

    anomaly_status = 0
    anomaly_score = 0.0
    model_ready = False

    # Check if we have enough samples to perform anomaly detection
    # We filter columns that are present in the current reading to fit the model
    current_keys = [k for k in numeric_reading.keys() if k != "timestamp"]
    
    # Convert buffer to DataFrame to check values
    df = pd.DataFrame(list(buffer))
    # Drop rows that have NaN in the columns we care about
    df_features = df[current_keys].dropna()

    if len(df_features) >= MIN_SAMPLES:
        try:
            # We fit Isolation Forest on the historical data
            clf = IsolationForest(contamination=CONTAMINATION, random_state=42)
            clf.fit(df_features)
            
            # Predict status of the current reading (the last one appended)
            current_row = df_features.iloc[[-1]]
            pred = clf.predict(current_row)[0]
            # score is the anomaly score (lower is more abnormal)
            score = clf.decision_function(current_row)[0]
            
            # 1 for anomaly (outlier, predicted -1), 0 for normal (inlier, predicted 1)
            anomaly_status = 1 if pred == -1 else 0
            anomaly_score = float(-score) # Inverted: higher means more anomalous
            model_ready = True
        except Exception as e:
            print(f"Error fitting Isolation Forest model for device {device_id}: {e}")

    # Prepare enriched payload
    enriched_payload = data.copy()
    enriched_payload["is_anomaly"] = anomaly_status
    enriched_payload["anomaly_score"] = anomaly_score
    enriched_payload["model_ready"] = int(model_ready)

    # Publish anomalies to output topic
    output_topic = f"{OUTPUT_TOPIC_PREFIX}{device_id}"
    try:
        client.publish(output_topic, json.dumps(enriched_payload))
        print(f"Processed reading for {device_id}: is_anomaly={anomaly_status}, score={anomaly_score:.4f} (buffer: {len(df_features)} samples)")
    except Exception as e:
        print(f"Error publishing anomaly message for device {device_id}: {e}")

def main():
    client = mqtt.Client()
    if MQTT_USER and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to MQTT broker at {MQTT_HOST}:{MQTT_PORT}...")
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, 60)
            break
        except Exception as e:
            print(f"MQTT connection failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)
            
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("Stopping anomaly detector...")
        client.disconnect()

if __name__ == "__main__":
    main()
