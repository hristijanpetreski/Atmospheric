import socket

from app.compat import json
from app.config import ConfigError

MAX_REQUEST = 4096
STATIC_PATH = "/app/www/index.html.gz"


def _send(connection, data):
    offset = 0
    while offset < len(data):
        sent = connection.send(data[offset:])
        if not sent:
            raise OSError("socket closed while sending")
        offset += sent


def parse_request(data):
    marker = data.find(b"\r\n\r\n")
    if marker < 0:
        raise ValueError("incomplete request")
    head = data[:marker].decode("utf-8")
    body = data[marker + 4 :]
    lines = head.split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) != 3:
        raise ValueError("invalid request line")
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.lower().strip()] = value.strip()
    return parts[0], parts[1].split("?", 1)[0], headers, body


def _send_headers(connection, status, content_type, length, extra=None):
    headers = [
        "HTTP/1.1 %s" % status,
        "Content-Type: %s" % content_type,
        "Content-Length: %d" % length,
        "Cache-Control: no-store",
        "Connection: close",
    ]
    if extra:
        headers.extend(extra)
    _send(connection, ("\r\n".join(headers) + "\r\n\r\n").encode())


def _send_json(connection, status, payload):
    body = json.dumps(payload).encode()
    _send_headers(connection, status, "application/json", len(body))
    _send(connection, body)


class WebServer:
    def __init__(self, status, get_config, save_config, scan_wifi):
        self.status = status
        self.get_config = get_config
        self.save_config = save_config
        self.scan_wifi = scan_wifi
        self.socket = None

    def start(self):
        address = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
        server = socket.socket()
        try:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except OSError:
            pass
        server.bind(address)
        server.listen(2)
        server.settimeout(0)
        self.socket = server
        print("Configuration server ready")

    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None

    def poll(self):
        if not self.socket:
            return
        try:
            connection, _ = self.socket.accept()
        except OSError:
            return
        try:
            connection.settimeout(1)
            data = bytearray()
            content_length = 0
            header_end = -1
            while len(data) < MAX_REQUEST:
                chunk = connection.recv(min(512, MAX_REQUEST - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if header_end < 0:
                    header_end = data.find(b"\r\n\r\n")
                    if header_end >= 0:
                        _, _, headers, _ = parse_request(data)
                        try:
                            content_length = int(headers.get("content-length", "0"))
                        except ValueError:
                            content_length = -1
                if header_end >= 0 and len(data) >= header_end + 4 + content_length:
                    break
            self._handle(connection, bytes(data))
        except (OSError, ValueError) as error:
            try:
                _send_json(connection, "400 Bad Request", {"error": str(error)})
            except OSError:
                pass
        finally:
            connection.close()

    def _handle(self, connection, data):
        method, path, headers, body = parse_request(data)
        if int(headers.get("content-length", "0")) > MAX_REQUEST:
            return _send_json(
                connection, "413 Payload Too Large", {"error": "request is too large"}
            )

        if method == "GET" and path in (
            "/",
            "/index.html",
            "/generate_204",
            "/hotspot-detect.html",
            "/ncsi.txt",
        ):
            return self._send_page(connection)
        if method == "GET" and path == "/health":
            payload = b"ok"
            _send_headers(connection, "200 OK", "text/plain", len(payload))
            return _send(connection, payload)
        if method == "GET" and path == "/api/status":
            return _send_json(connection, "200 OK", self.status())
        if method == "GET" and path == "/api/config":
            return _send_json(connection, "200 OK", self.get_config())
        if method == "GET" and path == "/api/wifi":
            return _send_json(connection, "200 OK", {"networks": self.scan_wifi()})
        if method == "POST" and path == "/api/config":
            if "application/json" not in headers.get("content-type", ""):
                return _send_json(
                    connection,
                    "415 Unsupported Media Type",
                    {"error": "application/json is required"},
                )
            try:
                submitted = json.loads(body.decode("utf-8"))
                self.save_config(submitted)
                return _send_json(
                    connection,
                    "200 OK",
                    {"saved": True, "restarting": True},
                )
            except (ValueError, ConfigError) as error:
                return _send_json(
                    connection, "422 Unprocessable Entity", {"error": str(error)}
                )
        return _send_json(connection, "404 Not Found", {"error": "not found"})

    def _send_page(self, connection):
        try:
            size = __import__("os").stat(STATIC_PATH)[6]
            _send_headers(
                connection,
                "200 OK",
                "text/html; charset=utf-8",
                size,
                ["Content-Encoding: gzip"],
            )
            with open(STATIC_PATH, "rb") as handle:
                while True:
                    chunk = handle.read(512)
                    if not chunk:
                        break
                    _send(connection, chunk)
        except OSError:
            _send_json(
                connection,
                "503 Service Unavailable",
                {"error": "setup page is missing"},
            )
