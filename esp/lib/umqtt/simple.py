# Lightweight MQTT 3.1.1 client derived from micropython-lib umqtt.simple.
# SPDX-License-Identifier: MIT

import socket
import struct


class MQTTException(Exception):
    pass


class MQTTClient:
    def __init__(
        self,
        client_id,
        server,
        port=0,
        user=None,
        password=None,
        keepalive=0,
        ssl=None,
        ssl_params=None,
    ):
        self.client_id = client_id
        self.server = server
        self.port = port or 1883
        self.user = user
        self.password = password
        self.keepalive = keepalive
        self.ssl = ssl
        self.ssl_params = ssl_params or {}
        self.socket = None
        self.packet_id = 0

    def _send_string(self, value):
        if isinstance(value, str):
            value = value.encode()
        self.socket.write(struct.pack("!H", len(value)))
        self.socket.write(value)

    def connect(self, clean_session=True, timeout=None):
        address = socket.getaddrinfo(self.server, self.port)[0][-1]
        self.socket = socket.socket()
        if timeout is not None:
            self.socket.settimeout(timeout)
        self.socket.connect(address)
        if self.ssl:
            import ssl

            self.socket = ssl.wrap_socket(self.socket, **self.ssl_params)

        flags = 0x02 if clean_session else 0
        if self.user is not None:
            flags |= 0x80
        if self.password is not None:
            flags |= 0x40
        payload_length = 2 + len(self.client_id)
        if self.user is not None:
            payload_length += 2 + len(self.user)
        if self.password is not None:
            payload_length += 2 + len(self.password)
        remaining = 10 + payload_length
        packet = bytearray(b"\x10\0\0\0\0")
        index = 1
        while remaining > 0x7F:
            packet[index] = (remaining & 0x7F) | 0x80
            remaining >>= 7
            index += 1
        packet[index] = remaining
        self.socket.write(packet, index + 1)
        self.socket.write(b"\x00\x04MQTT\x04")
        self.socket.write(bytes((flags, self.keepalive >> 8, self.keepalive & 0xFF)))
        self._send_string(self.client_id)
        if self.user is not None:
            self._send_string(self.user)
        if self.password is not None:
            self._send_string(self.password)
        response = self.socket.read(4)
        if response is None or len(response) != 4 or response[0] != 0x20:
            raise MQTTException("invalid CONNACK")
        if response[3] != 0:
            raise MQTTException(response[3])
        return response[2] & 1

    def disconnect(self):
        if self.socket:
            self.socket.write(b"\xe0\0")
            self.socket.close()
            self.socket = None

    def publish(self, topic, message, retain=False, qos=0):
        if isinstance(topic, str):
            topic = topic.encode()
        if isinstance(message, str):
            message = message.encode()
        packet = bytearray(b"\x30\0\0\0\0")
        packet[0] |= qos << 1 | retain
        remaining = 2 + len(topic) + len(message) + (2 if qos else 0)
        index = 1
        while remaining > 0x7F:
            packet[index] = (remaining & 0x7F) | 0x80
            remaining >>= 7
            index += 1
        packet[index] = remaining
        self.socket.write(packet, index + 1)
        self._send_string(topic)
        if qos:
            self.packet_id += 1
            self.packet_id &= 0xFFFF
            packet_id = self.packet_id or 1
            self.socket.write(struct.pack("!H", packet_id))
        self.socket.write(message)
