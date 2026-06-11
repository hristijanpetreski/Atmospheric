#!/usr/bin/env python3
"""Exercise the running detector through MQTT and assert an outlier is detected."""

import argparse
import json
import queue
import random
import sys
import threading
import uuid

import paho.mqtt.client as mqtt


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser.parse_args()


def main():
    args = parse_args()
    device_id = f"detector-test-{uuid.uuid4().hex[:8]}"
    input_topic = f"atmospheric/sensors/{device_id}"
    output_topic = f"atmospheric/anomalies/{device_id}"
    responses = queue.Queue()
    subscribed = threading.Event()
    connection_error = []

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(connected_client, userdata, flags, reason_code, properties):
        del userdata, flags, properties
        if reason_code.is_failure:
            connection_error.append(str(reason_code))
            subscribed.set()
            return
        connected_client.subscribe(output_topic)

    def on_subscribe(connected_client, userdata, mid, reason_codes, properties):
        del connected_client, userdata, mid, reason_codes, properties
        subscribed.set()

    def on_message(connected_client, userdata, message):
        del connected_client, userdata
        responses.put(json.loads(message.payload.decode("utf-8")))

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    try:
        client.connect(args.host, args.port, keepalive=60)
        client.loop_start()
        if not subscribed.wait(args.timeout):
            raise RuntimeError("timed out connecting and subscribing to MQTT")
        if connection_error:
            raise RuntimeError(f"MQTT connection failed: {connection_error[0]}")

        random.seed(42)
        print(f"Warming up {device_id} with {args.samples} normal readings...")
        last_response = None
        for _ in range(args.samples):
            reading = {
                "temperature": 22.0 + random.uniform(-0.3, 0.3),
                "humidity": 55.0 + random.uniform(-0.8, 0.8),
                "pressure": 1013.0 + random.uniform(-0.2, 0.2),
            }
            client.publish(input_topic, json.dumps(reading)).wait_for_publish(
                timeout=args.timeout
            )
            last_response = responses.get(timeout=args.timeout)

        if last_response is None or last_response["model_ready"] != 0:
            raise AssertionError(
                "warm-up contract failed; --samples must match MIN_SAMPLES"
            )

        outlier = {"temperature": 85.0, "humidity": 5.0, "pressure": 940.0}
        client.publish(input_topic, json.dumps(outlier)).wait_for_publish(
            timeout=args.timeout
        )
        result = responses.get(timeout=args.timeout)

        print(json.dumps(result, indent=2, sort_keys=True))
        if result["model_ready"] != 1:
            raise AssertionError("model was not ready after warm-up")
        if result["is_anomaly"] != 1:
            raise AssertionError("extreme reading was not classified as an anomaly")
        if result["anomaly_score"] <= 0:
            raise AssertionError("anomaly score did not cross the zero threshold")

        print("PASS: the detector flagged the injected outlier.")
        return 0
    except queue.Empty:
        print(
            "FAIL: timed out waiting for an anomaly response. "
            "Check the detector and Mosquitto logs.",
            file=sys.stderr,
        )
        return 1
    except (AssertionError, OSError, RuntimeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
