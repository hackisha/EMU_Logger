# -*- coding: utf-8 -*-
"""
ADXL345 I²C 가속도 센서 리더
- 기본 주소: 0x53
- Full-Resolution 모드(10~13bit, 3.9mg/LSB)로 설정
- g 단위로 변환해 콜백 및 Firebase로 전송
"""

from typing import Callable, Dict, Any, Optional
from time import sleep
try:
    from smbus2 import SMBus
except ImportError:
    SMBus = None

from .firebase_client import FirebaseClient

# ADXL345 레지스터
REG_DEVID       = 0x00
REG_POWER_CTL   = 0x2D
REG_DATA_FORMAT = 0x31
REG_BW_RATE     = 0x2C
REG_DATAX0      = 0x32  # X0~Z1 (6바이트 연속)

ADXL345_ADDR = 0x53

class AccelWorker:
    def __init__(
        self,
        i2c_bus: int = 1,
        address: int = ADXL345_ADDR,
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None,
        fb: Optional[FirebaseClient] = None
    ):
        self.i2c_bus_num = i2c_bus
        self.addr = address
        self.on_update = on_update
        self.fb = fb
        self.bus: Optional[SMBus] = None
        self.enabled = SMBus is not None

    def start(self):
        if not self.enabled:
            raise RuntimeError("smbus2 가 설치되어 있지 않습니다. pip3 install smbus2")
        self.bus = SMBus(self.i2c_bus_num)
        # 칩 확인 (선택)
        try:
            devid = self.bus.read_byte_data(self.addr, REG_DEVID)
            # ADXL345 DEVID는 0xE5이지만, 호환 칩도 있으므로 강한 체크는 생략
        except Exception as e:
            raise RuntimeError(f"ADXL345 접근 실패: {e}")

        # 전원/포맷/대역폭 설정
        # BW_RATE: 0x0A → 100Hz
        self.bus.write_byte_data(self.addr, REG_BW_RATE, 0x0A)
        # DATA_FORMAT: FULL_RES(비트3)=1, ±2g(비트0~1=0) → 0x08
        self.bus.write_byte_data(self.addr, REG_DATA_FORMAT, 0x08)
        # POWER_CTL: Measure(비트3)=1 → 0x08
        self.bus.write_byte_data(self.addr, REG_POWER_CTL, 0x08)
        sleep(0.02)

    def read_once(self):
        """한 번 읽어 g 단위로 반환/콜백/Firebase 전송"""
        if not self.bus:
            return
        try:
            data = self.bus.read_i2c_block_data(self.addr, REG_DATAX0, 6)
            # 리틀엔디언 16비트 부호값
            y = self._to_int16(data[1] << 8 | data[0])
            x = self._to_int16(data[3] << 8 | data[2])
            z = self._to_int16(data[5] << 8 | data[4])

            # Full-Resolution: scale ≈ 3.9 mg/LSB → 0.0039 g/LSB
            lsb_g = 0.0039
            ax_g = x * lsb_g
            ay_g = -y * lsb_g
            az_g = z * lsb_g

            out = {"ax_g": ax_g, "ay_g": ay_g, "az_g": az_g}
            if self.on_update:
                self.on_update(out)

            if self.fb:
                from .config import FB_PATHS
                payload = {"ts": self.fb.now_ms(), **out}
                # 실시간/시계열 모두 저장
                self.fb.patch(FB_PATHS["ACC_REALTIME"], payload)
                self.fb.post(FB_PATHS["ACC_TIMESERIES"], payload)

        except Exception:
            # 센서 노이즈/일시 오류는 무시
            return

    @staticmethod
    def _to_int16(v: int) -> int:
        return v - 65536 if v & 0x8000 else v

    def shutdown(self):
        if self.bus:
            try:
                self.bus.close()
            except Exception:
                pass
            self.bus = None
