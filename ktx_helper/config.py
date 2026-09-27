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

    if not isinstance(raw, dict):
        raise ConfigError("설정 파일 최상위는 객체여야 합니다")

    raw_trips = raw.get("trips")
    if not isinstance(raw_trips, list) or not raw_trips:
        raise ConfigError("trips 에 최소 1개의 여정이 필요합니다")

    trips = [_parse_trip(t, i) for i, t in enumerate(raw_trips)]
    reminders = _parse_reminders(raw.get("reminders", {}) or {})
    notify = _parse_notify(raw.get("notify", {}) or {})

    od_raw = raw.get("opendata", {}) or {}
    opendata = OpenDataConfig(service_key=str(od_raw.get("service_key", "")))

    return Config(trips=trips, reminders=reminders, notify=notify, opendata=opendata)
