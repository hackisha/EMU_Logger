# -*- coding: utf-8 -*-

import time

try:
    import RPi.GPIO as GPIO
    IS_RASPI = True
except (ImportError, RuntimeError):
    IS_RASPI = False

from .config import BUTTON_PIN, LOGGING_LED_PIN, ERROR_LED_PIN, WIFI_LED_PIN

class GpioController:
    def __init__(self):
        self.is_raspi = IS_RASPI
        if self.is_raspi:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(LOGGING_LED_PIN, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(ERROR_LED_PIN, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(WIFI_LED_PIN, GPIO.OUT, initial=GPIO.LOW)

    def read_button_pressed(self) -> bool:
        """눌림 시 True (풀업 기준 active-low)"""
        if not self.is_raspi:
            return False
        return GPIO.input(BUTTON_PIN) == GPIO.LOW

    def set_logging_led(self, state: bool):
        if not self.is_raspi: return
        GPIO.output(LOGGING_LED_PIN, GPIO.HIGH if state else GPIO.LOW)

    def blink_logging_led_once(self, on_ms: int = 50):
        if not self.is_raspi: return
        GPIO.output(LOGGING_LED_PIN, GPIO.LOW)
        time.sleep(on_ms / 1000.0)
        GPIO.output(LOGGING_LED_PIN, GPIO.HIGH)

    def set_error_led(self, state: bool):
        if not self.is_raspi: return
        GPIO.output(ERROR_LED_PIN, GPIO.HIGH if state else GPIO.LOW)

    def set_wifi_led(self, state: bool):
        if not self.is_raspi: return
        GPIO.output(WIFI_LED_PIN, GPIO.HIGH if state else GPIO.LOW)

    def cleanup(self):
        if self.is_raspi:
            GPIO.cleanup()
