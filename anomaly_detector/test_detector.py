import json
import os
import unittest
from unittest.mock import patch

from detector import (
    AnomalyDetector,
    Config,
    DeviceDetector,
    InvalidReading,
    get_device_id,
)


class TestConfig(unittest.TestCase):
    def test_rejects_invalid_window(self):
        with patch.dict(
            os.environ,
            {"MIN_SAMPLES": "30", "WINDOW_SIZE": "20"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "WINDOW_SIZE"):
                Config.from_env()

    def test_rejects_invalid_contamination(self):
        with patch.dict(os.environ, {"CONTAMINATION": "0.75"}, clear=True):
            with self.assertRaisesRegex(ValueError, "CONTAMINATION"):
                Config.from_env()

    def test_rejects_invalid_robust_threshold(self):
        with patch.dict(os.environ, {"ROBUST_Z_THRESHOLD": "0"}, clear=True):
            with self.assertRaisesRegex(ValueError, "ROBUST_Z_THRESHOLD"):
                Config.from_env()


class TestDeviceDetector(unittest.TestCase):
    def setUp(self):
        self.config = Config(window_size=50, min_samples=30, contamination=0.05)
        self.detector = DeviceDetector(self.config)

    @staticmethod
    def normal_reading(index):
        offset = ((index % 7) - 3) / 10
        return {
            "temperature": 22.0 + offset,
            "humidity": 55.0 + offset * 2,
            "pressure": 1013.0 + offset / 2,
        }

    def test_warmup_and_extreme_outlier(self):
        for index in range(self.config.min_samples):
            result = self.detector.process(self.normal_reading(index))
            self.assertEqual(result.model_ready, 0)
            self.assertEqual(result.is_anomaly, 0)

        result = self.detector.process(
            {"temperature": 85.0, "humidity": 5.0, "pressure": 940.0}
        )

        self.assertEqual(result.model_ready, 1)
        self.assertEqual(result.is_anomaly, 1)
        self.assertGreater(result.anomaly_score, 0)
        self.assertEqual(result.model_samples, 31)

    def test_constant_sensor_detects_a_changed_value(self):
        detector = DeviceDetector(
            Config(window_size=10, min_samples=3, robust_z_threshold=6.0)
        )
        for _ in range(3):
            detector.process({"temperature": 22.0})

        result = detector.process({"temperature": 23.0})

        self.assertEqual(result.is_anomaly, 1)
        self.assertGreater(result.anomaly_score, 0)

    def test_bmp280_null_humidity_uses_available_sensor_fields(self):
        result = self.detector.process(
            {"temperature": 22.0, "humidity": None, "pressure": 1013.0}
        )

        self.assertEqual(self.detector.feature_names, ("temperature", "pressure"))
        self.assertEqual(result.model_ready, 0)

    def test_feature_schema_stays_stable(self):
        self.detector.process(
            {"temperature": 22.0, "humidity": 55.0, "pressure": 1013.0}
        )

        with self.assertRaisesRegex(InvalidReading, "humidity"):
            self.detector.process(
                {"temperature": 22.0, "humidity": None, "pressure": 1013.0}
            )

    def test_ignores_numeric_metadata(self):
        self.detector.process(
            {
                "temperature": 22.0,
                "humidity": 55.0,
                "pressure": 1013.0,
                "timestamp": 1781200000,
                "battery_mv": 3900,
            }
        )

        self.assertEqual(
            self.detector.feature_names, ("temperature", "humidity", "pressure")
        )


class TestAnomalyDetector(unittest.TestCase):
    def test_keeps_device_histories_separate(self):
        detector = AnomalyDetector(Config(window_size=10, min_samples=2))

        first = detector.process("indoor", {"temperature": 20.0})
        second = detector.process("outdoor", {"temperature": 5.0})

        self.assertEqual(first["model_samples"], 1)
        self.assertEqual(second["model_samples"], 1)
        self.assertEqual(set(detector.devices), {"indoor", "outdoor"})

    def test_enriched_payload_is_json_serializable(self):
        detector = AnomalyDetector(Config(window_size=10, min_samples=2))
        enriched = detector.process("test", {"temperature": 20.0})

        json.dumps(enriched)

    def test_device_id_comes_from_last_topic_segment(self):
        self.assertEqual(get_device_id("atmospheric/sensors/lab"), "lab")
        with self.assertRaises(ValueError):
            get_device_id("atmospheric/sensors/")


if __name__ == "__main__":
    unittest.main()
