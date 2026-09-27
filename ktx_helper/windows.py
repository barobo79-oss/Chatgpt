"""취소표가 잘 나오는 시간대 계산.

코레일은 취소표를 특정 시각에 몰아서 풀지 않지만, 구조적으로 취소·잔여석이
집중되는 '통계적으로 유리한 창(window)'이 있습니다. 이 모듈은 여정의 출발일을
기준으로 그 창들을 계산해, 사용자가 그 시각에 **직접 공식 앱을 열어** 예매하도록
알림 시각 목록을 만듭니다.

근거가 되는 취소·잔여석 발생 패턴(2026년 기준, 일반에 알려진 규칙):
  1. 자정 전후(23:40~00:20): 결제 기한이 지난 미결제 예약이 자동 취소됩니다.
  2. 새벽(03:10~03:30): 시스템 정산 후 잔여석이 일괄 반영되는 경우가 있습니다.
  3. 출발 전날(D-1) 낮: 일정 확정에 따른 개인 취소가 늘어납니다.
  4. 출발 당일 아침: 출발 직전 취소가 나옵니다.

이 값들은 '보장'이 아니라 '확률이 높은 시간대'입니다. 가장 확실한 방법은 아래
:func:`is_waitlist_recommended` 가 안내하는 **공식 예약대기** 등록입니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

# (시각, 설명) — 매일 반복되는 유리한 창.
_DAILY_WINDOWS: tuple[tuple[time, str], ...] = (
    (time(23, 40), "미결제 예약 자동취소 시작 시간대(자정 전)"),
    (time(0, 15), "미결제 예약 자동취소 마무리 시간대(자정 직후)"),
    (time(3, 20), "새벽 정산 후 잔여석 반영 시간대"),
    (time(12, 0), "낮 개인 일정취소 시간대"),
    (time(19, 0), "퇴근 후 일정취소 시간대"),
)


@dataclass(frozen=True)
class Reminder:
    """알림 한 건: 언제, 무엇을, 왜."""

    when: datetime
    trip_name: str
    reason: str

    def line(self) -> str:
        return f"{self.when.strftime('%Y-%m-%d %H:%M')}  [{self.trip_name}]  {self.reason}"


def default_reminders(
    trip_name: str,
    travel_date: date,
    days_before: int,
    departure_time: time | None = None,
) -> list[Reminder]:
    """출발일 기준으로 기본 알림 시각들을 만듭니다.

    Args:
        trip_name: 여정 이름(알림 문구에 표시).
        travel_date: 출발 날짜.
        days_before: 출발 며칠 전부터 매일 알림을 넣을지.
        departure_time: 알면 출발 당일 '출발 1시간 전' 알림을 추가합니다.
    """
    reminders: list[Reminder] = []
    for offset in range(days_before, -1, -1):
        day = travel_date - timedelta(days=offset)
        for slot, reason in _DAILY_WINDOWS:
            reminders.append(
                Reminder(
                    when=datetime.combine(day, slot),
                    trip_name=trip_name,
                    reason=f"D-{offset} 취소표 확인 — {reason}",
                )
            )

    if departure_time is not None:
        dep_dt = datetime.combine(travel_date, departure_time)
        reminders.append(
            Reminder(
                when=dep_dt - timedelta(hours=1),
                trip_name=trip_name,
                reason="출발 1시간 전 — 막판 취소표 확인",
            )
        )

    # 시간순 정렬 + 중복 제거.
    unique: dict[datetime, Reminder] = {}
    for r in sorted(reminders, key=lambda x: x.when):
        unique.setdefault(r.when, r)
    return list(unique.values())


def upcoming(reminders: list[Reminder], now: datetime | None = None) -> list[Reminder]:
    """지금 이후로 남은 알림만 돌려줍니다."""
    now = now or datetime.now()
    return [r for r in reminders if r.when >= now]


def is_waitlist_recommended(travel_date: date, now: datetime | None = None) -> tuple[bool, str]:
    """공식 '예약대기'를 권장하는지와 그 이유를 돌려줍니다.

    예약대기는 좌석이 매진이어도 걸어 두면 취소분이 생겼을 때 코레일이 자동으로
    배정해 주는 공식 기능입니다. 사람이 계속 새로고침할 필요가 없어, 개인 사용자
    입장에서 가장 확실하고 합법적인 방법입니다.
    """
    now = now or datetime.now()
    days_left = (travel_date - now.date()).days
    if days_left < 0:
        return False, "이미 지난 날짜입니다."
    if days_left == 0:
        return True, "출발 당일입니다. 예약대기가 열려 있으면 즉시 등록하고, 취소표 창 시간대에 앱을 확인하세요."
    return (
        True,
        "매진이라면 지금 바로 코레일+ 앱에서 '예약대기'를 등록하세요. "
        "취소분이 생기면 코레일이 자동 배정하고 알림톡/문자로 알려 줍니다.",
    )
