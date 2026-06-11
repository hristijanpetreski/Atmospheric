import os

from app.compat import json

CONFIG_PATH = "/config.json"
CONFIG_TMP_PATH = "/config.tmp"
CONFIG_BACKUP_PATH = "/config.bak"

DEFAULTS = {
    "version": 1,
    "wifi": {"ssid": "", "password": ""},
    "mqtt": {
        "host": "",
        "port": 1883,
        "topic": "atmospheric/sensors/device",
        "username": "",
        "password": "",
    },
    "sampling_interval": 30,
}


class ConfigError(ValueError):
    pass


def _text(value, name, max_length, required=False, strip=True):
    if not isinstance(value, str):
        raise ConfigError("%s must be text" % name)
    if strip:
        value = value.strip()
    if required and not value:
        raise ConfigError("%s is required" % name)
    if len(value) > max_length:
        raise ConfigError("%s is too long" % name)
    return value


def defaults():
    return {
        "version": DEFAULTS["version"],
        "wifi": dict(DEFAULTS["wifi"]),
        "mqtt": dict(DEFAULTS["mqtt"]),
        "sampling_interval": DEFAULTS["sampling_interval"],
    }


def validate(data, require_wifi=True):
    if not isinstance(data, dict):
        raise ConfigError("configuration must be an object")

    wifi = data.get("wifi", {})
    mqtt = data.get("mqtt", {})
    if not isinstance(wifi, dict) or not isinstance(mqtt, dict):
        raise ConfigError("wifi and mqtt must be objects")

    ssid = _text(wifi.get("ssid", ""), "WiFi SSID", 32, require_wifi, False)
    wifi_password = _text(wifi.get("password", ""), "WiFi password", 64, strip=False)
    host = _text(mqtt.get("host", ""), "MQTT host", 253, require_wifi)
    topic = _text(mqtt.get("topic", ""), "MQTT topic", 256, require_wifi)
    username = _text(mqtt.get("username", ""), "MQTT username", 128, strip=False)
    mqtt_password = _text(mqtt.get("password", ""), "MQTT password", 256, strip=False)

    try:
        port = int(mqtt.get("port", 1883))
        interval = int(data.get("sampling_interval", 30))
    except (TypeError, ValueError):
        raise ConfigError("port and sampling interval must be numbers")

    if port < 1 or port > 65535:
        raise ConfigError("MQTT port must be between 1 and 65535")
    if interval < 5 or interval > 86400:
        raise ConfigError("sampling interval must be between 5 and 86400 seconds")

    return {
        "version": 1,
        "wifi": {"ssid": ssid, "password": wifi_password},
        "mqtt": {
            "host": host,
            "port": port,
            "topic": topic,
            "username": username,
            "password": mqtt_password,
        },
        "sampling_interval": interval,
    }


def merge_submission(submitted, current=None):
    current = current or defaults()
    wifi = submitted.get("wifi", {})
    mqtt = submitted.get("mqtt", {})
    merged = {
        "version": 1,
        "wifi": {
            "ssid": wifi.get("ssid", ""),
            "password": wifi.get("password", "")
            or current.get("wifi", {}).get("password", ""),
        },
        "mqtt": {
            "host": mqtt.get("host", ""),
            "port": mqtt.get("port", 1883),
            "topic": mqtt.get("topic", ""),
            "username": mqtt.get("username", ""),
            "password": mqtt.get("password", "")
            or current.get("mqtt", {}).get("password", ""),
        },
        "sampling_interval": submitted.get("sampling_interval", 30),
    }
    return validate(merged)


def public(config):
    if not config:
        config = defaults()
    return {
        "version": config.get("version", 1),
        "wifi": {
            "ssid": config.get("wifi", {}).get("ssid", ""),
            "password_set": bool(config.get("wifi", {}).get("password")),
        },
        "mqtt": {
            "host": config.get("mqtt", {}).get("host", ""),
            "port": config.get("mqtt", {}).get("port", 1883),
            "topic": config.get("mqtt", {}).get("topic", ""),
            "username": config.get("mqtt", {}).get("username", ""),
            "password_set": bool(config.get("mqtt", {}).get("password")),
        },
        "sampling_interval": config.get("sampling_interval", 30),
    }


def load(path=CONFIG_PATH, backup_path=CONFIG_BACKUP_PATH):
    for candidate in (path, backup_path):
        try:
            with open(candidate, "r") as handle:
                return validate(json.load(handle))
        except (OSError, ValueError, ConfigError):
            pass
    return None


def save(
    config,
    path=CONFIG_PATH,
    tmp_path=CONFIG_TMP_PATH,
    backup_path=CONFIG_BACKUP_PATH,
):
    config = validate(config)
    with open(tmp_path, "w") as handle:
        json.dump(config, handle)
        handle.flush()
    try:
        os.remove(backup_path)
    except OSError:
        pass
    try:
        os.rename(path, backup_path)
    except OSError:
        pass
    try:
        os.rename(tmp_path, path)
    except OSError:
        try:
            os.rename(backup_path, path)
        except OSError:
            pass
        raise
    try:
        os.remove(backup_path)
    except OSError:
        pass
    return config
