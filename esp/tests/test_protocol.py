import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.payload import encode_payload
from app.web_server import parse_request


class ProtocolTests(unittest.TestCase):
    def test_mqtt_payload_matches_ingestion_shape(self):
        payload = json.loads(
            encode_payload(
                {"temperature": 22.41, "humidity": 57.28, "pressure": 1012.84}
            )
        )
        self.assertEqual(
            payload,
            {"temperature": 22.41, "humidity": 57.28, "pressure": 1012.84},
        )

    def test_http_request_parser(self):
        request = (
            b"POST /api/config?source=test HTTP/1.1\r\n"
            b"Host: 192.168.4.1\r\n"
            b"Content-Type: application/json\r\n\r\n"
            b'{"sampling_interval":30}'
        )
        method, path, headers, body = parse_request(request)
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/api/config")
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(json.loads(body), {"sampling_interval": 30})


if __name__ == "__main__":
    unittest.main()
