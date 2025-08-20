# -*- coding: utf-8 -*-

import json
import time
from typing import Any, Dict, Optional
import requests
from .config import FIREBASE_DB_URL, FIREBASE_AUTH, FIREBASE_ENABLE

class FirebaseClient:
    def __init__(self, base_url: str = FIREBASE_DB_URL, auth: Optional[str] = FIREBASE_AUTH, enabled: bool = FIREBASE_ENABLE):
        self.base_url = base_url
        self.auth = auth
        self.enabled = enabled and bool(base_url)

    def _url(self, path: str) -> str:
        path = path if path.startswith("/") else ("/" + path)
        url = f"{self.base_url}{path}.json"
        if self.auth:
            url += f"?auth={self.auth}"
        return url

    def patch(self, path: str, data: Dict[str, Any]) -> bool:
        """경로에 현재 상태를 업데이트 (부분 갱신)"""
        if not self.enabled:
            return True
        try:
            r = requests.patch(self._url(path), data=json.dumps(data), timeout=3)
            r.raise_for_status()
            return True
        except requests.RequestException:
            return False

    def post(self, path: str, data: Dict[str, Any]) -> bool:
        """경로에 새 노드로 추가(시계열 적합)"""
        if not self.enabled:
            return True
        try:
            r = requests.post(self._url(path), data=json.dumps(data), timeout=3)
            r.raise_for_status()
            return True
        except requests.RequestException:
            return False

    @staticmethod
    def now_ms() -> int:
        return int(time.time() * 1000)
