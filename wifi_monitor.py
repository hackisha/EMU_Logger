# -*- coding: utf-8 -*-

import socket
import threading
from .gpio_ctrl import GpioController

def start_wifi_monitor(gpio: GpioController, stop_event: threading.Event) -> threading.Thread:
    def _loop():
        while not stop_event.is_set():
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=2)
                gpio.set_wifi_led(True)
            except OSError:
                gpio.set_wifi_led(False)
            stop_event.wait(10)
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t
