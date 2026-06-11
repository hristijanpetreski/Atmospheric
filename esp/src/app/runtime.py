import gc

import machine

from app import config as config_store
from app.compat import sleep_ms, ticks_add, ticks_diff, ticks_ms
from app.mqtt_client import SensorPublisher
from app.network_manager import NetworkManager
from app.sensor import EnvironmentalSensor
from app.web_server import WebServer


class Application:
    def __init__(self):
        self.config = config_store.load()
        self.network = NetworkManager()
        self.network.configure(self.config)
        self.publisher = SensorPublisher(self.config) if self.config else None
        self.sensor = None
        self.last_reading = None
        self.sensor_error = None
        self.restart_at = None
        self.next_sample = ticks_ms()
        self.next_sensor_retry = ticks_ms()
        self.web = WebServer(
            self.status,
            self.public_config,
            self.save_config,
            self.network.scan,
        )

    def setup(self):
        if self.config:
            print("Connecting to WiFi:", self.config["wifi"]["ssid"])
            if not self.network.connect():
                self.network.start_access_point()
        else:
            print("No valid configuration found")
            self.network.start_access_point()
        self._start_sensor()
        self.web.start()

    def _start_sensor(self):
        try:
            self.sensor = EnvironmentalSensor()
            self.sensor_error = None
            print("BME280 ready")
        except (OSError, ValueError) as error:
            self.sensor = None
            self.sensor_error = str(error)
            self.next_sensor_retry = ticks_add(ticks_ms(), 30000)
            print("Sensor unavailable:", error)

    def public_config(self):
        return config_store.public(self.config)

    def save_config(self, submitted):
        merged = config_store.merge_submission(submitted, self.config)
        self.config = config_store.save(merged)
        self.restart_at = ticks_add(ticks_ms(), 1000)

    def status(self):
        try:
            free_heap = gc.mem_free()
        except AttributeError:
            free_heap = None
        return {
            "wifi": {
                "connected": self.network.is_connected(),
                "ap_active": self.network.ap_active,
                "ip": self.network.ip_address(),
            },
            "mqtt": {"connected": bool(self.publisher and self.publisher.connected)},
            "sensor": {
                "ready": self.sensor is not None,
                "error": self.sensor_error,
                "reading": self.last_reading,
            },
            "free_heap": free_heap,
        }

    def loop(self):
        now = ticks_ms()
        connected = self.network.maintain()
        if not connected and self.publisher:
            self.publisher.disconnect()

        self.web.poll()

        if self.restart_at is not None and ticks_diff(now, self.restart_at) >= 0:
            print("Restarting with new configuration")
            sleep_ms(100)
            machine.reset()

        if self.sensor is None and ticks_diff(now, self.next_sensor_retry) >= 0:
            self._start_sensor()

        if self.config and self.sensor and ticks_diff(now, self.next_sample) >= 0:
            interval_ms = self.config["sampling_interval"] * 1000
            self.next_sample = ticks_add(now, interval_ms)
            try:
                self.last_reading = self.sensor.read()
                self.sensor_error = None
                print("Sensor:", self.last_reading)
                if connected and self.publisher:
                    self.publisher.publish(self.last_reading)
            except (OSError, RuntimeError, ValueError) as error:
                self.sensor_error = str(error)
                print("Sensor read failed:", error)
        gc.collect()
        sleep_ms(25)


def run():
    application = Application()
    try:
        application.setup()
        while True:
            application.loop()
    except KeyboardInterrupt:
        raise
    except Exception as error:
        print("Fatal application error:", error)
        sleep_ms(3000)
        machine.reset()
