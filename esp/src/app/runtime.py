import gc
import sys

import machine

from app import config as config_store
from app.compat import sleep_ms, ticks_add, ticks_diff, ticks_ms
from app.network_manager import NetworkManager


def log_heap(label):
    try:
        print(label, "heap:", gc.mem_free())
    except AttributeError:
        pass


class Application:
    def __init__(self):
        self.config = config_store.load()
        self.network = NetworkManager()
        self.network.configure(self.config)
        self.publisher = None
        self.publisher_error = None
        self.sensor = None
        self.last_reading = None
        self.sensor_error = None
        self.restart_at = None
        self.next_sample = ticks_ms()
        self.next_sensor_retry = ticks_ms()
        self.next_publisher_retry = ticks_ms()
        self.web = None

    def setup(self):
        gc.collect()
        log_heap("Startup")
        if self.config:
            self._start_sensor()
            print("Connecting to WiFi:", self.config["wifi"]["ssid"])
            if self.network.connect():
                self._start_normal_mode()
                self._start_web()
            else:
                self._stop_sensor()
                self.network.start_access_point()
                self._start_web()
        else:
            print("No valid configuration found")
            self.network.start_access_point()
            self._start_web()

    def _start_web(self):
        if self.web:
            return
        gc.collect()
        log_heap("Before web")
        from app.web_server import WebServer

        self.web = WebServer(
            self.status,
            self.public_config,
            self.save_config,
            self.network.scan,
        )
        self.web.start()
        gc.collect()
        log_heap("Web ready")

    def _stop_web(self):
        if not self.web:
            return
        self.web.close()
        self.web = None
        try:
            del sys.modules["app.web_server"]
        except KeyError:
            pass
        gc.collect()

    def _start_normal_mode(self):
        gc.collect()
        if self.sensor:
            log_heap("Before MQTT")
            self._start_publisher()
        gc.collect()
        log_heap("Normal mode")

    def _start_publisher(self):
        if self.publisher:
            return
        try:
            from app.mqtt_client import SensorPublisher

            self.publisher = SensorPublisher(self.config)
            self.publisher_error = None
        except MemoryError as error:
            self.publisher = None
            self.publisher_error = str(error)
            self.next_publisher_retry = ticks_add(ticks_ms(), 30000)
            print("MQTT unavailable:", error)

    def _start_sensor(self):
        try:
            gc.collect()
            log_heap("Before sensor")
            from app.sensor import EnvironmentalSensor

            self.sensor = EnvironmentalSensor()
            self.sensor_error = None
            print(self.sensor.model, "ready")
        except (OSError, ValueError, MemoryError) as error:
            self.sensor = None
            self.sensor_error = str(error)
            self.next_sensor_retry = ticks_add(ticks_ms(), 30000)
            print("Sensor unavailable:", error)

    def _stop_sensor(self):
        self.sensor = None
        for module in ("app.sensor", "bme280"):
            try:
                del sys.modules[module]
            except KeyError:
                pass
        gc.collect()

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
            "mqtt": {
                "connected": bool(self.publisher and self.publisher.connected),
                "error": self.publisher_error,
            },
            "sensor": {
                "ready": self.sensor is not None,
                "model": self.sensor.model if self.sensor else None,
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

        if (connected or self.network.ap_active) and self.web is None:
            self._start_web()
        if self.web:
            self.web.poll()

        if self.restart_at is not None and ticks_diff(now, self.restart_at) >= 0:
            print("Restarting with new configuration")
            sleep_ms(100)
            machine.reset()

        if (
            connected
            and self.sensor
            and self.publisher is None
            and ticks_diff(now, self.next_publisher_retry) >= 0
        ):
            self._start_publisher()

        if (
            connected
            and self.sensor is None
            and ticks_diff(now, self.next_sensor_retry) >= 0
        ):
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
