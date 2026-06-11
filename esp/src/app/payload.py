from app.compat import json


def encode_payload(reading):
    return json.dumps(reading)
