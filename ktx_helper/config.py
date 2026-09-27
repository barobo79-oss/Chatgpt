"""설정 파일 로드·검증.

의존성을 줄이려고 YAML 대신 JSON을 씁니다(파이썬 표준 라이브러리만 사용).
설정 예시는 ``ktx_config.example.json`` 을 참고하세요.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

# 코레일 열차 종별(참고용). 실제 예매는 사용자가 앱에서 하므로 표시·필터 용도입니다.
TRAIN_TYPES = {
    "KTX": "KTX/KTX-산천/KTX-이음",
    "ITX": "ITX-새마을/ITX-청춘/ITX-마음",
    "MUGUNGHWA": "무궁화호/누리로",
    "ALL": "전체",
}

# 웹 설정 화면의 역 선택 드롭다운용(노선별). 알림 기능엔 역 '이름'만 쓰이므로
# 코드가 없어도 됩니다. 공공데이터 조회에는 opendata.STATION_SEED 의 코드가 쓰입니다.
STATIONS_BY_LINE: dict[str, list[str]] = {
    "수도권": ["서울", "용산", "청량리", "영등포", "광명", "수원", "상봉"],
    "경부·경전(부산·대구·창원)": [
        "천안아산", "오송", "대전", "김천구미", "동대구", "밀양", "구포", "부산",
        "신경주", "울산", "포항", "진영", "창원중앙", "창원", "마산", "진주",
    ],
    "호남(광주·목포)": ["공주", "익산", "정읍", "광주송정", "나주", "목포"],
    "전라(여수)": ["전주", "남원", "순천", "여천", "여수엑스포"],
    "강릉·강원": ["만종", "횡성", "둔내", "평창", "진부", "강릉", "정동진"],
    "중앙(안동·영주)": ["원주", "제천", "단양", "풍기", "영주", "안동"],
}

# 귀성/귀경 방향 판단용 수도권 역.
SEOUL_METRO: set[str] = {"서울", "용산", "청량리", "영등포", "광명", "수원", "상봉"}

# 명절 연휴 범위(설·추석). 이름 자동 생성에서 '귀성/귀경/연휴'를 붙입니다.
HOLIDAY_RANGES: list[tuple[date, date, str]] = [
    (date(2026, 2, 16), date(2026, 2, 18), "설"),
    (date(2026, 9, 24), date(2026, 9, 26), "추석"),
    (date(2027, 2, 6), date(2027, 2, 9), "설"),
    (date(2027, 9, 14), date(2027, 9, 16), "추석"),
]

# 단일 공휴일(날짜 → 여정 이름에 붙일 이름).
HOLIDAYS: dict[str, str] = {
    "2026-01-01": "신정", "2026-03-01": "삼일절", "2026-03-02": "삼일절",
    "2026-05-05": "어린이날", "2026-05-24": "부처님오신날", "2026-05-25": "부처님오신날",
    "2026-06-06": "현충일", "2026-08-15": "광복절", "2026-10-03": "개천절",
    "2026-10-09": "한글날", "2026-12-25": "크리스마스",
    "2027-01-01": "신정", "2027-03-01": "삼일절", "2027-05-05": "어린이날",
    "2027-05-13": "부처님오신날", "2027-06-06": "현충일", "2027-06-07": "현충일",
    "2027-08-15": "광복절", "2027-08-16": "광복절", "2027-10-03": "개천절",
    "2027-10-04": "개천절", "2027-10-09": "한글날", "2027-12-25": "크리스마스",
}


def suggest_trip_name(dep: str, arr: str, when: date | str | None) -> str:
    """출발·도착역과 날짜로 여정 이름을 자동 제안합니다.

    명절 연휴면 방향에 따라 '추석 귀성/귀경/연휴', 단일 공휴일이면 그 이름,
    주말/금요일이면 '주말 여행'을 붙입니다. 예: '서울→부산 추석 귀성'.
    """
    dep = (dep or "").strip()
    arr = (arr or "").strip()
    if not dep or not arr:
        return ""
    base = f"{dep}→{arr}"

    d: date | None
    if when is None or when == "":
        d = None
    elif isinstance(when, date):
        d = when
    else:
        try:
            d = date.fromisoformat(str(when))
        except ValueError:
            d = None
    if d is None:
        return base

    for start, end, name in HOLIDAY_RANGES:
        if start <= d <= end:
            if dep in SEOUL_METRO and arr not in SEOUL_METRO:
                return f"{base} {name} 귀성"
            if arr in SEOUL_METRO and dep not in SEOUL_METRO:
                return f"{base} {name} 귀경"
            return f"{base} {name} 연휴"

    key = d.isoformat()
    if key in HOLIDAYS:
        return f"{base} {HOLIDAYS[key]}"
    if d.weekday() in (4, 5, 6):  # 금·토·일
        return f"{base} 주말 여행"
    return base


class ConfigError(ValueError):
    """설정 파일이 잘못됐을 때 발생합니다."""


@dataclass
class Trip:
    """감시(알림)할 여정 하나."""

    name: str
    dep: str
    arr: str
    travel_date: date
    time_from: time
    time_to: time
    train_type: str = "KTX"
    passengers: int = 1

    def window_label(self) -> str:
        return f"{self.time_from.strftime('%H:%M')}~{self.time_to.strftime('%H:%M')}"

    def summary(self) -> str:
        return (
            f"[{self.name}] {self.dep}→{self.arr} "
            f"{self.travel_date.isoformat()} {self.window_label()} "
            f"({TRAIN_TYPES.get(self.train_type, self.train_type)}, {self.passengers}명)"
        )


@dataclass
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class WebhookConfig:
    enabled: bool = False
    url: str = ""


@dataclass
class NotifyConfig:
    desktop: bool = True
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)


@dataclass
class ReminderConfig:
    use_default_windows: bool = True
    days_before: int = 3
    extra_times: list[datetime] = field(default_factory=list)


@dataclass
class OpenDataConfig:
    service_key: str = ""


@dataclass
class Config:
    trips: list[Trip]
    reminders: ReminderConfig = field(default_factory=ReminderConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    opendata: OpenDataConfig = field(default_factory=OpenDataConfig)


def _parse_date(value: str, ctx: str) -> date:
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ConfigError(f"{ctx}: 날짜는 'YYYY-MM-DD' 형식이어야 합니다 (받은 값: {value!r})")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(f"{ctx}: 잘못된 날짜입니다 ({value!r}) — {exc}") from exc


def _parse_time(value: str, ctx: str) -> time:
    if not isinstance(value, str) or not _TIME_RE.match(value):
        raise ConfigError(f"{ctx}: 시각은 'HH:MM' 형식이어야 합니다 (받은 값: {value!r})")
    hour, minute = (int(part) for part in value.split(":"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ConfigError(f"{ctx}: 시각 범위를 벗어났습니다 ({value!r})")
    return time(hour, minute)


def _parse_trip(raw: dict[str, Any], index: int) -> Trip:
    ctx = f"trips[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{ctx}: 여정은 객체여야 합니다")

    for key in ("dep", "arr", "date"):
        if key not in raw:
            raise ConfigError(f"{ctx}: 필수 항목 '{key}' 가 없습니다")

    travel_date = _parse_date(raw["date"], ctx)
    time_from = _parse_time(raw.get("time_from", "00:00"), f"{ctx}.time_from")
    time_to = _parse_time(raw.get("time_to", "23:59"), f"{ctx}.time_to")
    if time_to < time_from:
        raise ConfigError(f"{ctx}: time_to({time_to}) 가 time_from({time_from}) 보다 빠릅니다")

    train_type = str(raw.get("train_type", "KTX")).upper()
    if train_type not in TRAIN_TYPES:
        raise ConfigError(
            f"{ctx}: train_type 은 {list(TRAIN_TYPES)} 중 하나여야 합니다 (받은 값: {train_type!r})"
        )

    passengers = raw.get("passengers", 1)
    if not isinstance(passengers, int) or passengers < 1 or passengers > 9:
        raise ConfigError(f"{ctx}: passengers 는 1~9 사이 정수여야 합니다 (받은 값: {passengers!r})")

    dep = str(raw["dep"]).strip()
    arr = str(raw["arr"]).strip()
    if not dep or not arr:
        raise ConfigError(f"{ctx}: 출발역/도착역이 비어 있습니다")
    if dep == arr:
        raise ConfigError(f"{ctx}: 출발역과 도착역이 같습니다 ({dep})")

    name = str(raw.get("name") or f"{dep}→{arr}").strip()
    return Trip(
        name=name,
        dep=dep,
        arr=arr,
        travel_date=travel_date,
        time_from=time_from,
        time_to=time_to,
        train_type=train_type,
        passengers=passengers,
    )


def _parse_reminders(raw: dict[str, Any]) -> ReminderConfig:
    if not isinstance(raw, dict):
        raise ConfigError("reminders 는 객체여야 합니다")
    cfg = ReminderConfig()
    cfg.use_default_windows = bool(raw.get("use_default_windows", True))

    days_before = raw.get("days_before", 3)
    if not isinstance(days_before, int) or not (0 <= days_before <= 30):
        raise ConfigError("reminders.days_before 는 0~30 사이 정수여야 합니다")
    cfg.days_before = days_before

    extra: list[datetime] = []
    for i, item in enumerate(raw.get("extra_times", []) or []):
        try:
            extra.append(datetime.strptime(str(item), "%Y-%m-%d %H:%M"))
        except ValueError as exc:
            raise ConfigError(
                f"reminders.extra_times[{i}] 는 'YYYY-MM-DD HH:MM' 형식이어야 합니다 (받은 값: {item!r})"
            ) from exc
    cfg.extra_times = extra
    return cfg


def _parse_notify(raw: dict[str, Any]) -> NotifyConfig:
    if not isinstance(raw, dict):
        raise ConfigError("notify 는 객체여야 합니다")
    cfg = NotifyConfig(desktop=bool(raw.get("desktop", True)))

    tg = raw.get("telegram", {}) or {}
    cfg.telegram = TelegramConfig(
        enabled=bool(tg.get("enabled", False)),
        bot_token=str(tg.get("bot_token", "")),
        chat_id=str(tg.get("chat_id", "")),
    )
    if cfg.telegram.enabled and (not cfg.telegram.bot_token or not cfg.telegram.chat_id):
        raise ConfigError("notify.telegram.enabled=true 이면 bot_token 과 chat_id 가 필요합니다")

    wh = raw.get("webhook", {}) or {}
    cfg.webhook = WebhookConfig(enabled=bool(wh.get("enabled", False)), url=str(wh.get("url", "")))
    if cfg.webhook.enabled and not cfg.webhook.url:
        raise ConfigError("notify.webhook.enabled=true 이면 url 이 필요합니다")
    return cfg


def load_config(path: str | Path) -> Config:
    """설정 파일을 읽어 검증된 :class:`Config` 로 돌려줍니다.

    Raises:
        ConfigError: 파일이 없거나 형식이 잘못됐습니다.
    """
    p = Path(path)
    if not p.is_file():
        raise ConfigError(
            f"설정 파일을 찾을 수 없습니다: {p}\n"
            f"'ktx_config.example.json' 을 복사해 'ktx_config.json' 을 만든 뒤 값을 채우세요."
        )
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"설정 파일 JSON 파싱 실패 ({p}): {exc}") from exc

    return build_config(raw)


def build_config(raw: dict[str, Any]) -> Config:
    """이미 파싱된 dict 를 검증해 :class:`Config` 로 만듭니다(웹앱/저장 전 검증용).

    Raises:
        ConfigError: 형식이 잘못됐습니다.
    """
    if not isinstance(raw, dict):
        raise ConfigError("설정 최상위는 객체여야 합니다")

    raw_trips = raw.get("trips")
    if not isinstance(raw_trips, list) or not raw_trips:
        raise ConfigError("여정을 최소 1개 추가해야 합니다")

    trips = [_parse_trip(t, i) for i, t in enumerate(raw_trips)]
    reminders = _parse_reminders(raw.get("reminders", {}) or {})
    notify = _parse_notify(raw.get("notify", {}) or {})

    od_raw = raw.get("opendata", {}) or {}
    opendata = OpenDataConfig(service_key=str(od_raw.get("service_key", "")))

    return Config(trips=trips, reminders=reminders, notify=notify, opendata=opendata)
