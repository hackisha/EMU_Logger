# -*- coding: utf-8 -*-

import serial
import pynmea2
from typing import Callable, Dict, Any, Optional
from .firebase_client import FirebaseClient

class GpsWorker:
    """
    - NMEA($GPRMC, $GPGGA) 파싱
    - 파싱 결과를 콜백으로 전달
    - Firebase로 실시간/시계열 전송(옵션)
    """
    def __init__(
        self,
        serial_port: str,
        baudrate: int,
        on_update: Callable[[Dict[str, Any]], None],
        fb: Optional[FirebaseClient] = None
    ):
        self.port = serial_port
        self.baudrate = baudrate
        self.on_update = on_update
        self.fb = fb
        self.ser: Optional[serial.Serial] = None

    def start(self):
        self.ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=1)

    def read_once(self):
        if not self.ser:
            return
        try:
            line = self.ser.readline().decode("utf-8", errors="ignore")
            if not line.startswith(("$GPRMC", "$GPGGA")):
                return

            msg = pynmea2.parse(line)
            out: Dict[str, Any] = {}

            if line.startswith("$GPRMC"):
                if getattr(msg, "status", "V") == "A":  # A = valid
                    out.update({
                        "Latitude": msg.latitude,
                        "Longitude": msg.longitude,
                        "GPS_Speed_KPH": (msg.spd_over_grnd or 0) * 1.852,
                    })
            elif line.startswith("$GPGGA"):
                if getattr(msg, "is_valid", False):
                    out.update({
                        "Satellites": msg.num_sats
                    })

            if out:
                # 콜백 (메모리 최신값 갱신 등)
                self.on_update(out)

                # Firebase
                if self.fb:
                    from .config import FB_PATHS
                    payload = {"ts": self.fb.now_ms(), **out}
                    self.fb.patch(FB_PATHS["GPS_REALTIME"], payload)
                    self.fb.post(FB_PATHS["GPS_TIMESERIES"], payload)

        except (pynmea2.ParseError, serial.SerialException, UnicodeDecodeError):
            # 무시하고 계속
            return

    def shutdown(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None
