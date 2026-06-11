from app.compat import json


def encode_payload(reading):
    return json.dumps(
        {
            "temperature": reading["temperature"],
            "humidity": reading["humidity"],
            "pressure": reading["pressure"],
        }
    )
