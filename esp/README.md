# Atmospheric MicroPython firmware

The firmware connects an ESP8266 or ESP32 to WiFi, reads a BME280, and
publishes JSON readings over MQTT. If WiFi configuration is missing or the
connection cannot be restored, it exposes a setup access point and web UI.

## Hardware defaults

| Board | SDA | SCL |
| --- | ---: | ---: |
| ESP8266 | GPIO4 | GPIO5 |
| ESP32 | GPIO21 | GPIO22 |

The sensor adapter probes BME280 addresses `0x76` and `0x77`. Change
`app/sensor.py` if the board uses different pins.

## Device behavior

- Configuration is stored in `/config.json`, separate from deployed code.
- The setup AP is named `Atmospheric-XXXX`; its password is printed over the
  serial console on boot.
- The setup page is available at `http://192.168.4.1`.
- A successful station connection disables the setup AP.
- The AP returns after WiFi has been unavailable for 60 seconds.
- Pressure is converted from Pa to hPa before publishing.

The MQTT payload is:

```json
{"temperature":22.41,"humidity":57.28,"pressure":1012.84}
```

## Build and deploy

From the repository root:

```bash
make test
make build
make deploy PORT=/dev/cu.usbserial-0001
```

`PORT=auto` is the default. Deployment uses `mpremote` through `uvx`, so it
does not require a global Python package installation.

Other useful commands:

```bash
make repl PORT=auto
make tree PORT=auto
make info PORT=auto
make reset PORT=auto
make clean
```

`make sync` copies `esp/build/` to the device without deleting
`/config.json`.

## Firmware layout

- `src/app/config.py`: validation, redaction, and recoverable writes
- `src/app/network_manager.py`: station and setup AP lifecycle
- `src/app/web_server.py`: bounded socket HTTP server
- `src/app/sensor.py`: BME280 adapter and unit conversion
- `src/app/mqtt_client.py`: MQTT connection and retry policy
- `src/app/runtime.py`: cooperative application scheduler
- `web/`: setup UI source
- `tools/build.mjs`: web minification, gzip, and deployment assembly
