import json
import math
import os
import statistics
from collections import deque
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt
from sklearn.ensemble import IsolationForest

DEFAULT_FEATURES = ("temperature", "humidity", "pressure")


class InvalidReading(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_user: str | None = None
    mqtt_password: str | None = None
    input_topic: str = "atmospheric/sensors/+"
    output_topic_prefix: str = "atmospheric/anomalies/"
    window_size: int = 1000
    min_samples: int = 30
    contamination: float = 0.05
    robust_z_threshold: float = 6.0
    features: tuple[str, ...] = DEFAULT_FEATURES

    @classmethod
    def from_env(cls) -> "Config":
        features = tuple(
            feature.strip()
            for feature in os.environ.get(
                "FEATURE_FIELDS", ",".join(DEFAULT_FEATURES)
            ).split(",")
            if feature.strip()
        )
        config = cls(
            mqtt_host=os.environ.get("MQTT_HOST", "localhost"),
            mqtt_port=int(os.environ.get("MQTT_PORT", "1883")),
            mqtt_user=os.environ.get("MQTT_USER") or None,
            mqtt_password=os.environ.get("MQTT_PASSWORD") or None,
            input_topic=os.environ.get("INPUT_TOPIC", "atmospheric/sensors/+"),
            output_topic_prefix=os.environ.get(
                "OUTPUT_TOPIC_PREFIX", "atmospheric/anomalies/"
            ),
            window_size=int(os.environ.get("WINDOW_SIZE", "1000")),
            min_samples=int(os.environ.get("MIN_SAMPLES", "30")),
            contamination=float(os.environ.get("CONTAMINATION", "0.05")),
            robust_z_threshold=float(os.environ.get("ROBUST_Z_THRESHOLD", "6.0")),
            features=features,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not 1 <= self.mqtt_port <= 65535:
            raise ValueError("MQTT_PORT must be between 1 and 65535")
        if self.min_samples < 2:
            raise ValueError("MIN_SAMPLES must be at least 2")
        if self.window_size < self.min_samples:
            raise ValueError("WINDOW_SIZE must be greater than or equal to MIN_SAMPLES")
        if not 0 < self.contamination <= 0.5:
            raise ValueError("CONTAMINATION must be greater than 0 and at most 0.5")
        if self.robust_z_threshold <= 0:
            raise ValueError("ROBUST_Z_THRESHOLD must be greater than 0")
        if not self.features:
            raise ValueError("FEATURE_FIELDS must contain at least one field")
        if not self.output_topic_prefix:
            raise ValueError("OUTPUT_TOPIC_PREFIX must not be empty")


@dataclass(frozen=True)
class Detection:
    is_anomaly: int
    anomaly_score: float
    model_ready: int
    model_samples: int


class DeviceDetector:
    def __init__(self, config: Config):
        self.config = config
        self.feature_names: tuple[str, ...] | None = None
        self.history: deque[list[float]] = deque(maxlen=config.window_size)

    def process(self, reading: dict[str, Any]) -> Detection:
        features = self._extract_features(reading)

        if len(self.history) < self.config.min_samples:
            self.history.append(features)
            return Detection(
                is_anomaly=0,
                anomaly_score=0.0,
                model_ready=0,
                model_samples=len(self.history),
            )

        model = IsolationForest(
            contamination=self.config.contamination,
            random_state=42,
            n_jobs=1,
        )
        model.fit(list(self.history))
        prediction = int(model.predict([features])[0])
        isolation_score = float(-model.decision_function([features])[0])
        robust_score = self._robust_deviation_score(features)
        score = max(isolation_score, robust_score)
        self.history.append(features)

        return Detection(
            is_anomaly=int(prediction == -1 or robust_score > 0),
            anomaly_score=score,
            model_ready=1,
            model_samples=len(self.history),
        )

    def _extract_features(self, reading: dict[str, Any]) -> list[float]:
        if self.feature_names is None:
            self.feature_names = tuple(
                name
                for name in self.config.features
                if _finite_number(reading.get(name)) is not None
            )
            if not self.feature_names:
                raise InvalidReading(
                    "reading has no finite numeric sensor fields from FEATURE_FIELDS"
                )

        values = [_finite_number(reading.get(name)) for name in self.feature_names]
        missing = [
            name for name, value in zip(self.feature_names, values) if value is None
        ]
        if missing:
            raise InvalidReading(
                f"reading is missing finite numeric values for: {', '.join(missing)}"
            )
        return [value for value in values if value is not None]

    def _robust_deviation_score(self, features: list[float]) -> float:
        largest_z_score = 0.0
        for index, current_value in enumerate(features):
            historical_values = [row[index] for row in self.history]
            center = statistics.median(historical_values)
            deviations = [abs(value - center) for value in historical_values]
            mad = statistics.median(deviations)

            if mad > 0:
                scale = 1.4826 * mad
            else:
                scale = statistics.pstdev(historical_values)

            if scale == 0:
                scale = max(abs(center) * 1e-6, 1e-9)
            z_score = abs(current_value - center) / scale
            largest_z_score = max(largest_z_score, z_score)

        return largest_z_score / self.config.robust_z_threshold - 1.0


class AnomalyDetector:
    def __init__(self, config: Config):
        self.config = config
        self.devices: dict[str, DeviceDetector] = {}

    def process(self, device_id: str, reading: dict[str, Any]) -> dict[str, Any]:
        detector = self.devices.setdefault(device_id, DeviceDetector(self.config))
        detection = detector.process(reading)
        return {
            **reading,
            "is_anomaly": detection.is_anomaly,
            "anomaly_score": detection.anomaly_score,
            "model_ready": detection.model_ready,
            "model_samples": detection.model_samples,
        }


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def get_device_id(topic: str) -> str:
    device_id = topic.rsplit("/", 1)[-1].strip()
    if not device_id or device_id in {"+", "#"}:
        raise ValueError(f"could not determine a device ID from topic {topic!r}")
    return device_id


def build_client(config: Config, detector: AnomalyDetector) -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if config.mqtt_user:
        client.username_pw_set(config.mqtt_user, config.mqtt_password)

    def on_connect(
        connected_client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        del userdata, flags, properties
        if reason_code.is_failure:
            print(f"MQTT connection failed: {reason_code}", flush=True)
            return
        connected_client.subscribe(config.input_topic)
        print(
            f"Connected to {config.mqtt_host}:{config.mqtt_port}; "
            f"subscribed to {config.input_topic}",
            flush=True,
        )

    def on_message(
        connected_client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage
    ) -> None:
        del userdata
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise InvalidReading("payload must be a JSON object")
            device_id = get_device_id(message.topic)
            enriched = detector.process(device_id, payload)
        except (UnicodeDecodeError, json.JSONDecodeError, InvalidReading, ValueError) as exc:
            print(f"Ignoring invalid reading on {message.topic}: {exc}", flush=True)
            return

        output_topic = f"{config.output_topic_prefix}{device_id}"
        publish = connected_client.publish(output_topic, json.dumps(enriched))
        if publish.rc != mqtt.MQTT_ERR_SUCCESS:
            print(
                f"Failed to publish reading for {device_id}: MQTT error {publish.rc}",
                flush=True,
            )
            return

        print(
            f"Processed {device_id}: anomaly={enriched['is_anomaly']} "
            f"score={enriched['anomaly_score']:.4f} "
            f"samples={enriched['model_samples']}",
            flush=True,
        )

    client.on_connect = on_connect
    client.on_message = on_message
    return client


def main() -> None:
    try:
        config = Config.from_env()
    except ValueError as exc:
        raise SystemExit(f"Invalid anomaly detector configuration: {exc}") from exc

    detector = AnomalyDetector(config)
    client = build_client(config, detector)
    print(
        f"Connecting to MQTT broker at {config.mqtt_host}:{config.mqtt_port}...",
        flush=True,
    )
    client.connect_async(config.mqtt_host, config.mqtt_port, keepalive=60)
    try:
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        print("Stopping anomaly detector...", flush=True)
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
