import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app import config


class ConfigTests(unittest.TestCase):
    def valid_config(self):
        return {
            "wifi": {"ssid": "Lab", "password": "secret123"},
            "mqtt": {
                "host": "broker.local",
                "port": 1883,
                "topic": "atmospheric/sensors/test",
                "username": "",
                "password": "",
            },
            "sampling_interval": 30,
        }

    def test_validation_normalizes_numbers(self):
        value = self.valid_config()
        value["mqtt"]["port"] = "1884"
        value["sampling_interval"] = "60"
        result = config.validate(value)
        self.assertEqual(result["mqtt"]["port"], 1884)
        self.assertEqual(result["sampling_interval"], 60)

    def test_merge_keeps_blank_passwords(self):
        current = config.validate(self.valid_config())
        current["mqtt"]["password"] = "broker-secret"
        submitted = self.valid_config()
        submitted["wifi"]["password"] = ""
        submitted["mqtt"]["password"] = ""
        result = config.merge_submission(submitted, current)
        self.assertEqual(result["wifi"]["password"], "secret123")
        self.assertEqual(result["mqtt"]["password"], "broker-secret")

    def test_public_config_redacts_secrets(self):
        result = config.public(config.validate(self.valid_config()))
        self.assertNotIn("password", result["wifi"])
        self.assertNotIn("password", result["mqtt"])
        self.assertTrue(result["wifi"]["password_set"])

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            tmp = os.path.join(directory, "config.tmp")
            backup = os.path.join(directory, "config.bak")
            expected = config.validate(self.valid_config())
            config.save(expected, path, tmp, backup)
            self.assertEqual(config.load(path, backup), expected)

    def test_load_uses_backup_when_primary_is_corrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            backup = os.path.join(directory, "config.bak")
            with open(path, "w") as handle:
                handle.write("{")
            with open(backup, "w") as handle:
                config.json.dump(config.validate(self.valid_config()), handle)
            self.assertIsNotNone(config.load(path, backup))

    def test_rejects_invalid_port_and_interval(self):
        value = self.valid_config()
        value["mqtt"]["port"] = 70000
        with self.assertRaises(config.ConfigError):
            config.validate(value)
        value = self.valid_config()
        value["sampling_interval"] = 1
        with self.assertRaises(config.ConfigError):
            config.validate(value)


if __name__ == "__main__":
    unittest.main()
