try:
    import ujson as json
except ImportError:
    import json

try:
    import utime as time
except ImportError:
    import time


def ticks_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.monotonic() * 1000)


def ticks_diff(a, b):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(a, b)
    return a - b


def ticks_add(value, delta):
    if hasattr(time, "ticks_add"):
        return time.ticks_add(value, delta)
    return value + delta


def sleep_ms(value):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(value)
    else:
        time.sleep(value / 1000)
