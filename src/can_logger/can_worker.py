# -*- coding: utf-8 -*-

import os
import struct
import can
from typing import Callable, Dict, Any, Optional
from .config import CAN_CHANNEL, CAN_BITRATE, EMU_IDS, EMU_ID_BASE
from .firebase_client import FirebaseClient

# ======== EMU 파서들 (원본과 동일) ========
def parse_emu_frame_0(data: bytes) -> Dict[str, Any]:
    if len(data) != 8: return {}
    return {
        "RPM": struct.unpack_from('<H', data, 0)[0],
        "TPS_percent": data[2] * 0.5,
        "IAT_C": struct.unpack_from('b', data, 3)[0],
        "MAP_kPa": struct.unpack_from('<H', data, 4)[0],
        "PulseWidth_ms": struct.unpack_from('<H', data, 6)[0] * 0.016129
    }
def parse_emu_frame_1(data: bytes) -> Dict[str, Any]:
    if len(data) != 8: return {}
    f = 0.0048828125
    return {
        "AnalogIn1_V": struct.unpack_from('<H', data, 0)[0] * f,
        "AnalogIn2_V": struct.unpack_from('<H', data, 2)[0] * f,
        "AnalogIn3_V": struct.unpack_from('<H', data, 4)[0] * f,
        "AnalogIn4_V": struct.unpack_from('<H', data, 6)[0] * f
    }
def parse_emu_frame_2(data: bytes) -> Dict[str, Any]:
    if len(data) != 8: return {}
    return {
        "VSS_kmh": struct.unpack_from('<H', data, 0)[0],
        "Baro_kPa": data[2],
        "OilTemp_C": data[3],
        "OilPressure_bar": data[4] * 0.0625,
        "FuelPressure_bar": data[5] * 0.0625,
        "CLT_C": struct.unpack_from('<h', data, 6)[0]
    }
def parse_emu_frame_3(data: bytes) -> Dict[str, Any]:
    if len(data) != 8: return {}
    return {
        "IgnAngle_deg": struct.unpack_from('b', data, 0)[0] * 0.5,
        "DwellTime_ms": data[1] * 0.05,
        "WBO_Lambda": data[2] * 0.0078125,
        "LambdaCorrection_percent": data[3] * 0.5,
        "EGT1_C": struct.unpack_from('<H', data, 4)[0],
        "EGT2_C": struct.unpack_from('<H', data, 6)[0]
    }
def parse_emu_frame_4(data: bytes) -> Dict[str, Any]:
    if len(data) != 8: return {}
    return {
        "Gear": data[0],
        "EmuTemp_C": data[1],
        "Batt_V": struct.unpack_from('<H', data, 2)[0] * 0.027,
        "CEL_Error": struct.unpack_from('<H', data, 4)[0],
        "Flags1": data[6],
        "Ethanol_percent": data[7]
    }
def parse_emu_frame_5(data: bytes) -> Dict[str, Any]:
    if len(data) != 8: return {}
    return {
        "DBW_Pos_percent": data[0] * 0.5,
        "DBW_Target_percent": data[1] * 0.5,
        "TC_drpm_raw": struct.unpack_from('<H', data, 2)[0],
        "TC_drpm": struct.unpack_from('<H', data, 4)[0],
        "TC_TorqueReduction_percent": data[6],
        "PitLimit_TorqueReduction_percent": data[7]
    }
def parse_emu_frame_6(data: bytes) -> Dict[str, Any]:
    if len(data) != 8: return {}
    f = 0.0048828125
    return {
        "AnalogIn5_V": struct.unpack_from('<H', data, 0)[0] * f,
        "AnalogIn6_V": struct.unpack_from('<H', data, 2)[0] * f,
        "OutFlags1": data[4],
        "OutFlags2": data[5],
        "OutFlags3": data[6],
        "OutFlags4": data[7]
    }
def parse_emu_frame_7(data: bytes) -> Dict[str, Any]:
    parsed = {
        "BoostTarget_kPa": struct.unpack_from('<H', data, 0)[0],
        "PWM1_DC_percent": data[2],
        "DSG_Mode": data[3]
    }
    if len(data) == 8:
        parsed.update({
            "LambdaTarget": data[4] * 0.01,
            "PWM2_DC_percent": data[5],
            "FuelUsed_L": struct.unpack_from('<H', data, 6)[0] * 0.01
        })
    return parsed

_PARSERS = {
    EMU_ID_BASE + 0: parse_emu_frame_0,
    EMU_ID_BASE + 1: parse_emu_frame_1,
    EMU_ID_BASE + 2: parse_emu_frame_2,
    EMU_ID_BASE + 3: parse_emu_frame_3,
    EMU_ID_BASE + 4: parse_emu_frame_4,
    EMU_ID_BASE + 5: parse_emu_frame_5,
    EMU_ID_BASE + 6: parse_emu_frame_6,
    EMU_ID_BASE + 7: parse_emu_frame_7,
}

def bring_up_can_interface(channel: str = CAN_CHANNEL, bitrate: int = CAN_BITRATE) -> None:
    os.system(f"sudo ip link set {channel} down")
    rc = os.system(f"sudo ip link set {channel} up type can bitrate {bitrate}")
    if rc != 0:
        raise IOError(f"{channel} 인터페이스 활성화 실패")

class CanWorker:
    """
    - CAN 프레임 수신
    - 파싱 결과를 콜백으로 전달
    - Firebase로 실시간/시계열 전송(옵션)
    """
    def __init__(
        self,
        on_parsed: Callable[[int, dict], None],
        fb: Optional[FirebaseClient] = None
    ):
        self.on_parsed = on_parsed
        self.bus: Optional[can.BusABC] = None
        self.fb = fb

    def start(self):
        bring_up_can_interface()
        self.bus = can.interface.Bus(channel=CAN_CHANNEL, bustype="socketcan")

    def recv_once(self, timeout: float = 0.02):
        if not self.bus:
            return
        msg = self.bus.recv(timeout=timeout)
        if msg is None:
            return
        parser = _PARSERS.get(msg.arbitration_id)
        if not parser:
            return
        parsed = parser(msg.data)
        if not parsed:
            return

        # 콜백 (CSV/상태 갱신 등)
        self.on_parsed(msg.arbitration_id, parsed)

        # Firebase: 실시간 상태 업데이트 + 시계열 추가
        if self.fb:
            from .config import FB_PATHS
            payload = {"ts": self.fb.now_ms(), **parsed, "id": hex(msg.arbitration_id)}
            self.fb.patch(FB_PATHS["CAN_REALTIME"], payload)
            self.fb.post(FB_PATHS["CAN_TIMESERIES"], payload)

    def shutdown(self):
        if self.bus:
            self.bus.shutdown()
            self.bus = None
