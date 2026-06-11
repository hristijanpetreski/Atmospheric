import machine
from umqtt.simple import MQTTClient, MQTTException

from app.compat import ticks_add, ticks_diff, ticks_ms
from app.payload import encode_payload


def client_id():
    suffix = "".join("%02x" % value for value in machine.unique_id())
    return ("atmospheric-" + suffix).encode()


class SensorPublisher:
    def __init__(self, config):
        self.config = config["mqtt"]
        self.client = None
        self.connected = False
        self.next_retry = ticks_ms()
        self.retry_delay = 2000

    def disconnect(self):
        if self.client:
            try:
                self.client.disconnect()
            except OSError:
                pass
        self.client = None
        self.connected = False

    def connect(self):
        now = ticks_ms()
        if self.connected:
            return True
        if ticks_diff(now, self.next_retry) < 0:
            return False
        try:
            username = self.config["username"] or None
            password = self.config["password"] or None
            self.client = MQTTClient(
                client_id(),
                self.config["host"],
                port=self.config["port"],
                user=username,
                password=password,
                keepalive=60,
            )
            self.client.connect(clean_session=True, timeout=5)
            self.connected = True
            self.retry_delay = 2000
            print("MQTT connected:", self.config["host"])
            return True
        except (OSError, MQTTException) as error:
            print("MQTT connection failed:", error)
            self.disconnect()
            self.next_retry = ticks_add(now, self.retry_delay)
            self.retry_delay = min(self.retry_delay * 2, 60000)
            return False

    def publish(self, reading):
        if not self.connect():
            return False
        try:
            payload = encode_payload(reading)
            self.client.publish(self.config["topic"], payload, retain=False, qos=0)
            return True
        except OSError as error:
            print("MQTT publish failed:", error)
            self.disconnect()
            return False
