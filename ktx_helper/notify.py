"""알림 채널.

우선순위: 콘솔(항상) → 데스크톱(가능하면) → 텔레그램/웹훅(설정 시).
표준 라이브러리만 씁니다(외부 패키지 불필요).

메타문 팁: 예매는 보통 휴대폰으로 하므로, 휴대폰으로 바로 뜨는 **텔레그램**
알림을 켜 두는 것이 가장 실용적입니다. 설정법은 README_KTX.md 참고.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from .config import NotifyConfig

_TIMEOUT = 20
_RETRIES = 3


def _console(title: str, message: str) -> None:
    print(f"\n🔔 {title}\n   {message}\n", flush=True)


def _desktop(title: str, message: str) -> bool:
    """OS별 데스크톱 알림. 성공하면 True. 실패는 조용히 False(다른 채널로 보완)."""
    system = platform.system()
    try:
        if system == "Darwin":
            script = f'display notification {json.dumps(message)} with title {json.dumps(title)}'
            subprocess.run(["osascript", "-e", script], check=True, timeout=_TIMEOUT)
            return True
        if system == "Linux":
            if shutil.which("notify-send"):
                subprocess.run(["notify-send", title, message], check=True, timeout=_TIMEOUT)
                return True
            return False
        if system == "Windows":
            # 외부 모듈 없이 PowerShell 메시지 박스로 확실히 화면에 띄웁니다.
            safe_msg = message.replace("'", "''")
            safe_title = title.replace("'", "''")
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms | Out-Null; "
                f"[System.Windows.Forms.MessageBox]::Show('{safe_msg}','{safe_title}') | Out-Null"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                check=True,
                timeout=_TIMEOUT,
            )
            return True
    except (subprocess.SubprocessError, OSError):
        return False
    return False


def _telegram(token: str, chat_id: str, title: str, message: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": f"🔔 {title}\n{message}", "disable_web_page_preview": "true"}
    ).encode("utf-8")
    last: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            with urllib.request.urlopen(url, data=data, timeout=_TIMEOUT) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, OSError) as exc:
            last = exc
            if attempt < _RETRIES - 1:
                time.sleep(2**attempt)  # 1초 → 2초 백오프
    print(f"   (텔레그램 전송 실패 {_RETRIES}회 시도: {last})", file=sys.stderr)
    return False


def _webhook(url: str, title: str, message: str) -> bool:
    payload = json.dumps({"title": title, "message": message}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError) as exc:
        print(f"   (웹훅 전송 실패: {exc})", file=sys.stderr)
        return False


def send_telegram(token: str, chat_id: str, title: str, message: str) -> bool:
    """텔레그램 한 채널로만 보냅니다(setup/notify-window 등에서 재사용)."""
    return _telegram(token, chat_id, title, message)


def telegram_creds_from_env() -> tuple[str, str]:
    """환경변수에서 텔레그램 자격증명을 읽습니다(GitHub Actions/작업 스케줄러용).

    KTX_TG_TOKEN, KTX_TG_CHAT 를 씁니다.
    """
    return os.environ.get("KTX_TG_TOKEN", "").strip(), os.environ.get("KTX_TG_CHAT", "").strip()


def send(cfg: NotifyConfig, title: str, message: str) -> dict[str, bool]:
    """설정된 모든 채널로 알림을 보냅니다. 채널별 성공 여부를 돌려줍니다."""
    results: dict[str, bool] = {}
    _console(title, message)
    results["console"] = True

    if cfg.desktop:
        results["desktop"] = _desktop(title, message)
    if cfg.telegram.enabled:
        results["telegram"] = _telegram(cfg.telegram.bot_token, cfg.telegram.chat_id, title, message)
    if cfg.webhook.enabled:
        results["webhook"] = _webhook(cfg.webhook.url, title, message)
    return results
