import sys
from array import array

import machine
from bme280 import BME280, BME280_OSAMPLE_2


def _default_pins():
    if sys.platform == "esp8266":
        return 4, 5
    return 21, 22


class EnvironmentalSensor:
    def __init__(self, sda=None, scl=None):
        default_sda, default_scl = _default_pins()
        sda = default_sda if sda is None else sda
        scl = default_scl if scl is None else scl
        self.i2c = machine.SoftI2C(
            sda=machine.Pin(sda), scl=machine.Pin(scl), freq=100000
        )
        addresses = self.i2c.scan()
        address = 0x76 if 0x76 in addresses else 0x77 if 0x77 in addresses else None
        if address is None:
            raise OSError("BME280 not found at 0x76 or 0x77")
        self.device = BME280(mode=BME280_OSAMPLE_2, address=address, i2c=self.i2c)
        self.buffer = array("f", [0.0, 0.0, 0.0])

    def read(self):
        temperature, pressure_pa, humidity = self.device.read_compensated_data(
            self.buffer
        )
        return {
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
            "pressure": round(pressure_pa / 100, 2),
        }
