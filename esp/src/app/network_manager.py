import machine
import network

from app.compat import sleep_ms, ticks_add, ticks_diff, ticks_ms

CONNECT_TIMEOUT_MS = 20000
AP_AFTER_MS = 60000
RETRY_MAX_MS = 60000


def _interface(station=True):
    if station:
        value = getattr(network, "STA_IF", getattr(network.WLAN, "IF_STA", 0))
    else:
        value = getattr(network, "AP_IF", getattr(network.WLAN, "IF_AP", 1))
    return network.WLAN(value)


def device_suffix():
    return "".join("%02x" % value for value in machine.unique_id())[-6:].upper()


class NetworkManager:
    def __init__(self):
        self.station = _interface(True)
        self.access_point = _interface(False)
        self.config = None
        self.ap_active = False
        self.disconnected_since = ticks_ms()
        self.next_retry = ticks_ms()
        self.retry_delay = 2000

    def configure(self, config):
        self.config = config

    def is_connected(self):
        return bool(self.station.active() and self.station.isconnected())

    def ip_address(self):
        if self.is_connected():
            return self.station.ifconfig()[0]
        if self.ap_active:
            return self.access_point.ifconfig()[0]
        return None

    def connect(self, timeout_ms=CONNECT_TIMEOUT_MS):
        if not self.config:
            return False
        wifi = self.config["wifi"]
        self.station.active(True)
        if self.station.isconnected():
            self.disconnected_since = None
            self.retry_delay = 2000
            self.stop_access_point()
            print("WiFi connected:", self.station.ifconfig()[0])
            return True
        self.station.connect(wifi["ssid"], wifi["password"])
        started = ticks_ms()
        while ticks_diff(ticks_ms(), started) < timeout_ms:
            if self.station.isconnected():
                self.disconnected_since = None
                self.retry_delay = 2000
                self.stop_access_point()
                print("WiFi connected:", self.station.ifconfig()[0])
                return True
            sleep_ms(250)
        try:
            self.station.disconnect()
        except OSError:
            pass
        self.disconnected_since = ticks_ms()
        return False

    def start_access_point(self):
        if self.ap_active:
            return
        suffix = device_suffix()
        ssid = "Atmospheric-%s" % suffix[-4:]
        password = "atm-%s" % suffix.lower()
        if len(password) < 8:
            password += "setup"
        self.access_point.active(True)
        try:
            self.access_point.config(ssid=ssid, key=password, security=3)
            configured_ssid = self.access_point.config("ssid")
        except (OSError, TypeError, ValueError):
            self.access_point.config(essid=ssid, password=password, authmode=3)
            configured_ssid = self.access_point.config("essid")
        self.ap_active = True
        print("Setup AP:", configured_ssid)
        print("Setup password:", password)
        print("Open http://%s" % self.access_point.ifconfig()[0])

    def stop_access_point(self):
        if self.access_point.active():
            self.access_point.active(False)
        self.ap_active = False

    def scan(self):
        self.station.active(True)
        results = []
        was_connected = self.station.isconnected()
        try:
            if not was_connected:
                try:
                    self.station.disconnect()
                except OSError:
                    pass
                sleep_ms(100)
            scanned = self.station.scan()
            for item in scanned:
                ssid = item[0].decode("utf-8", "ignore")
                if ssid and ssid not in results:
                    results.append(ssid)
        except OSError as error:
            print("WiFi scan failed:", error)
        if not was_connected and self.config:
            self.next_retry = ticks_add(ticks_ms(), 1000)
            self.retry_delay = 2000
        results.sort()
        return results[:20]

    def maintain(self):
        now = ticks_ms()
        if self.is_connected():
            if self.disconnected_since is not None:
                print("WiFi connected:", self.station.ifconfig()[0])
            self.disconnected_since = None
            self.retry_delay = 2000
            self.stop_access_point()
            return True

        if self.disconnected_since is None:
            self.disconnected_since = now

        if not self.config:
            self.start_access_point()
            return False

        if ticks_diff(now, self.disconnected_since) >= AP_AFTER_MS:
            self.start_access_point()

        if ticks_diff(now, self.next_retry) >= 0:
            wifi = self.config["wifi"]
            try:
                self.station.active(True)
                self.station.disconnect()
                self.station.connect(wifi["ssid"], wifi["password"])
            except OSError as error:
                print("WiFi retry failed:", error)
            self.next_retry = ticks_add(now, self.retry_delay)
            self.retry_delay = min(self.retry_delay * 2, RETRY_MAX_MS)
        return False
