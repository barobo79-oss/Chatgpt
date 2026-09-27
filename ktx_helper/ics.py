"""알림 시각을 캘린더(.ics) 파일로 내보내기.

생성된 .ics 를 구글 캘린더/휴대폰 캘린더에 가져오면, 프로그램을 계속 켜 두지
않아도 취소표 확인 시각에 캘린더 알림이 울립니다. 가장 가볍고 확실한 방법입니다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .windows import Reminder


def _fold(text: str) -> str:
    """RFC 5545: 특수문자 이스케이프."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _stamp(dt: datetime) -> str:
    # 로컬 시각(KST 가정) 기준. TZID 없이 floating time 으로 기록해 어떤 기기에서도
    # 그 지역 시각에 울리게 합니다.
    return dt.strftime("%Y%m%dT%H%M%S")


def to_ics(reminders: list[Reminder], alarm_minutes: int = 5) -> str:
    """알림 목록을 iCalendar 문자열로 변환합니다."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//KTX Helper//KR//",
        "CALSCALE:GREGORIAN",
    ]
    for i, r in enumerate(reminders):
        end = r.when + timedelta(minutes=10)
        uid = f"ktx-{_stamp(r.when)}-{i}@ktx-helper"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{_stamp(datetime.now())}",
            f"DTSTART:{_stamp(r.when)}",
            f"DTEND:{_stamp(end)}",
            f"SUMMARY:{_fold('🚄 KTX 취소표 확인 — ' + r.trip_name)}",
            f"DESCRIPTION:{_fold(r.reason + ' / 코레일+ 앱에서 직접 확인·예매하세요.')}",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_fold('KTX 취소표 확인 시간')}",
            f"TRIGGER:-PT{alarm_minutes}M",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def write_ics(reminders: list[Reminder], path: str | Path, alarm_minutes: int = 5) -> Path:
    p = Path(path)
    p.write_text(to_ics(reminders, alarm_minutes), encoding="utf-8")
    return p
