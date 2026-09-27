"""KTX 취소표 예약대기 도우미 — 명령줄 인터페이스.

사용 예:
    python -m ktx_helper guide                 # 취소표/예약대기 전략 요약
    python -m ktx_helper plan                   # 여정 확인 + 추천 알림 시각 출력
    python -m ktx_helper ics                     # 캘린더(.ics)로 알림 내보내기
    python -m ktx_helper remind                  # 알림 스케줄러 실행(프로그램 켜 둠)
    python -m ktx_helper trains                  # 공공데이터로 열차 시간표 조회(선택)
    python -m ktx_helper test                    # 알림 채널 테스트
"""

from __future__ import annotations

import argparse
import json
import sys
import time as _time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from . import __version__, notify
from .config import Config, ConfigError, load_config
from .ics import write_ics
from .windows import Reminder, default_reminders, is_waitlist_recommended, upcoming

DEFAULT_CONFIG = "ktx_config.json"

GUIDE = """
════════════════════════════════════════════════════════════════════
  🚄 KTX 표, 합법적으로 가장 효과적으로 잡는 법 (2026년 기준)
════════════════════════════════════════════════════════════════════

[1] 가장 확실한 방법 = 공식 '예약대기'
    - 원하는 열차가 매진이면 코레일+ 앱에서 '예약대기'를 신청하세요.
    - 취소분이 생기면 코레일이 '자동으로' 배정하고 알림톡/문자로 알려 줍니다.
    - 새로고침을 계속할 필요가 없어 개인에게 가장 유리합니다. (최대 9명, 열차별 신청)

[2] 취소표가 잘 나오는 시간대를 노리세요
    - 자정 전후(23:40~00:20): 결제 안 한 예약이 자동 취소됩니다.
    - 새벽 03:10~03:30: 정산 후 잔여석이 반영되기도 합니다.
    - 출발 전날 낮 / 출발 당일 아침: 개인 일정취소가 늘어납니다.
    → 이 도우미가 그 시각에 알림을 보내면, 직접 앱을 열어 확인하세요.

[3] 예매 오픈 시간을 지키세요 (명절 등)
    - 명절 승차권은 지정된 예매일에 대량으로 풀립니다.
    - 접속이 몰리면 대기열이 뜹니다. 미리 로그인·결제수단을 준비해 두세요.

[4] 하지 말아야 할 것 (중요)
    - 로그인 자동화·좌석 자동예매 '매크로'는 코레일 약관 위반입니다.
      → 계정 정지·예매 제한을 받을 수 있고, 코레일은 매크로 탐지 솔루션으로
        하루 수천~수만 건을 차단하고 있습니다(2026년).
    - 형법상 업무방해죄가 적용된 사례가 있어, 개인용이라도 법적 위험이 있습니다.
      영업 목적 부정판매는 철도사업법상 과태료(최대 1천만원) 대상입니다.
    → 그래서 이 도우미는 '알림 + 예약대기 안내'까지만 하고, 예매는 사람이 합니다.
════════════════════════════════════════════════════════════════════
"""


def _load(args: argparse.Namespace) -> Config:
    return load_config(args.config)


def _all_reminders(cfg: Config) -> list[Reminder]:
    reminders: list[Reminder] = []
    if cfg.reminders.use_default_windows:
        for trip in cfg.trips:
            reminders += default_reminders(
                trip_name=trip.name,
                travel_date=trip.travel_date,
                days_before=cfg.reminders.days_before,
                departure_time=trip.time_from,
            )
    for extra in cfg.reminders.extra_times:
        reminders.append(Reminder(when=extra, trip_name="사용자 지정", reason="직접 지정한 확인 시각"))
    return sorted(reminders, key=lambda r: r.when)


def cmd_guide(_args: argparse.Namespace) -> int:
    print(GUIDE)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    cfg = _load(args)
    print(f"\n📋 등록된 여정 {len(cfg.trips)}개\n" + "-" * 60)
    for trip in cfg.trips:
        print("  " + trip.summary())
        ok, msg = is_waitlist_recommended(trip.travel_date)
        mark = "✅" if ok else "⛔"
        print(f"     {mark} 예약대기: {msg}")

    reminders = upcoming(_all_reminders(cfg))
    print(f"\n⏰ 앞으로 남은 추천 확인 시각 {len(reminders)}개 (가까운 20개)\n" + "-" * 60)
    for r in reminders[:20]:
        print("  " + r.line())
    if len(reminders) > 20:
        print(f"  ... 외 {len(reminders) - 20}개")
    print("\n팁: 'ics' 명령으로 캘린더에 넣거나, 'remind' 로 실시간 알림을 받으세요.\n")
    return 0


def cmd_ics(args: argparse.Namespace) -> int:
    cfg = _load(args)
    reminders = upcoming(_all_reminders(cfg))
    if not reminders:
        print("내보낼 알림이 없습니다(모든 여정이 과거이거나 알림이 비었습니다).")
        return 1
    out = write_ics(reminders, args.out)
    print(f"✅ {len(reminders)}개 알림을 캘린더 파일로 저장했습니다: {out}")
    print("   구글 캘린더 → 설정 → 가져오기, 또는 휴대폰 캘린더 앱에서 이 파일을 여세요.")
    return 0


def cmd_trains(args: argparse.Namespace) -> int:
    cfg = _load(args)
    try:
        from .opendata import OpenDataError, search_trains
    except ImportError as exc:  # pragma: no cover
        print(f"공공데이터 모듈 로드 실패: {exc}", file=sys.stderr)
        return 1

    exit_code = 0
    for trip in cfg.trips:
        print(f"\n🚄 {trip.summary()}\n" + "-" * 60)
        try:
            runs = search_trains(
                dep=trip.dep,
                arr=trip.arr,
                travel_date=trip.travel_date,
                train_type=trip.train_type,
                service_key=cfg.opendata.service_key,
            )
        except OpenDataError as exc:
            print(f"  조회 실패: {exc}")
            exit_code = 1
            continue

        in_window = [
            r
            for r in runs
            if trip.time_from.strftime("%H:%M") <= r.dep_time <= trip.time_to.strftime("%H:%M")
        ]
        chosen = in_window or runs
        if not chosen:
            print("  해당 조건의 열차가 없습니다.")
            continue
        for r in chosen:
            print("  " + r.line())
        print("\n  ※ 위는 시간표이며 실시간 잔여석이 아닙니다. 예매·취소표 확인은 코레일+ 앱에서 하세요.")
    return exit_code


def cmd_test(args: argparse.Namespace) -> int:
    cfg = _load(args)
    results = notify.send(
        cfg.notify,
        "KTX 도우미 테스트",
        "알림이 정상 동작합니다. 취소표 시간대에 이렇게 알려 드릴게요.",
    )
    print("채널별 결과:", ", ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in results.items()))
    return 0 if all(results.values()) else 1


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _save_telegram_to_config(config_path: str, token: str, chat_id: str) -> None:
    """텔레그램 설정을 config 파일에 병합 저장합니다(없으면 예시에서 생성)."""
    p = Path(config_path)
    if p.is_file():
        data = json.loads(p.read_text(encoding="utf-8"))
    else:
        example = Path("ktx_config.example.json")
        data = json.loads(example.read_text(encoding="utf-8")) if example.is_file() else {"trips": []}
    notify_block = data.setdefault("notify", {})
    notify_block.setdefault("desktop", True)
    tg = notify_block.setdefault("telegram", {})
    tg.update({"enabled": True, "bot_token": token, "chat_id": str(chat_id)})
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _telegram_creds(args: argparse.Namespace) -> tuple[str, str]:
    """자격증명 우선순위: 환경변수 → config 파일."""
    token, chat_id = notify.telegram_creds_from_env()
    if token and chat_id:
        return token, chat_id
    try:
        cfg = load_config(args.config)
    except ConfigError:
        return token, chat_id
    if cfg.notify.telegram.enabled:
        return cfg.notify.telegram.bot_token, cfg.notify.telegram.chat_id
    return token, chat_id


def cmd_setup_telegram(args: argparse.Namespace) -> int:
    token = (args.bot_token or "").strip()
    if not token:
        try:
            token = input("텔레그램 봇 토큰(@BotFather 에서 /newbot 으로 발급): ").strip()
        except EOFError:
            print("봇 토큰이 필요합니다. --bot-token 으로 전달하세요.", file=sys.stderr)
            return 2
    if not token:
        print("봇 토큰이 비었습니다.", file=sys.stderr)
        return 2

    try:
        updates = _get_json(f"https://api.telegram.org/bot{token}/getUpdates")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"텔레그램 서버 요청 실패: {exc}", file=sys.stderr)
        return 1
    if not updates.get("ok"):
        print(f"봇 토큰이 유효하지 않습니다: {updates.get('description')}", file=sys.stderr)
        return 1

    chats: dict[str, str] = {}
    for upd in updates.get("result", []):
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        if cid is not None:
            chats[str(cid)] = chat.get("username") or chat.get("first_name") or str(cid)

    if not chats:
        print(
            "최근 대화를 찾지 못했습니다. 아래 순서로 해 주세요:\n"
            "  1) 텔레그램에서 방금 만든 봇과의 대화창을 연다\n"
            "  2) 봇에게 아무 메시지(예: 안녕)나 보낸다\n"
            "  3) 이 명령을 다시 실행한다",
            file=sys.stderr,
        )
        return 1

    if args.chat_id:
        chat_id = args.chat_id
    elif len(chats) == 1:
        chat_id = next(iter(chats))
    else:
        print("여러 대화가 감지됐습니다. --chat-id 로 하나를 지정해 다시 실행하세요:")
        for cid, name in chats.items():
            print(f"  {cid}  ({name})")
        return 1

    _save_telegram_to_config(args.config, token, chat_id)
    ok = notify.send_telegram(
        token, chat_id, "KTX 도우미", "설정 완료! 이제 취소표 시간대에 여기로 알려 드릴게요. 🚄"
    )
    print(f"✅ 텔레그램 설정을 {args.config} 에 저장했습니다 (chat_id={chat_id}).")
    print(f"   테스트 메시지 전송: {'성공 — 폰을 확인하세요!' if ok else '실패(토큰/네트워크 확인)'}")
    return 0 if ok else 1


def cmd_notify_window(args: argparse.Namespace) -> int:
    """한 번 실행되는 리마인더 발송(작업 스케줄러/GitHub Actions cron 용).

    지금이 취소표가 잘 나오는 시각이라는 전제로, 텔레그램으로 '지금 확인하세요'
    알림을 1회 보냅니다. --until 이후면 조용히 종료합니다.
    """
    token, chat_id = _telegram_creds(args)
    if not token or not chat_id:
        print(
            "텔레그램 자격증명이 없습니다. 환경변수 KTX_TG_TOKEN/KTX_TG_CHAT 또는 "
            "'setup-telegram' 으로 설정하세요.",
            file=sys.stderr,
        )
        return 2

    if args.until:
        try:
            until = datetime.strptime(args.until, "%Y-%m-%d").date()
        except ValueError:
            print("--until 은 'YYYY-MM-DD' 형식이어야 합니다.", file=sys.stderr)
            return 2
        if datetime.now().date() > until:
            print(f"출발일({until})이 지나 발송하지 않습니다.")
            return 0

    title = args.title or "🚄 KTX 취소표 확인 시간"
    message = args.message or (
        "지금 코레일+ 앱에서 취소표/예약대기를 확인하세요! "
        "(취소·잔여석이 잘 나오는 시간대입니다)"
    )
    ok = notify.send_telegram(token, chat_id, title, message)
    print("전송:", "성공" if ok else "실패")
    return 0 if ok else 1


def cmd_remind(args: argparse.Namespace) -> int:
    cfg = _load(args)
    reminders = upcoming(_all_reminders(cfg))
    if not reminders:
        print("예정된 알림이 없습니다. 'plan' 으로 여정/날짜를 확인하세요.")
        return 1

    print(f"⏰ 스케줄러 시작: 남은 알림 {len(reminders)}개. Ctrl+C 로 종료.")
    print(f"   다음 알림: {reminders[0].line()}")
    ok, msg = is_waitlist_recommended(cfg.trips[0].travel_date)
    if ok:
        print(f"   💡 지금 먼저 할 일: {msg}")

    pending = list(reminders)
    try:
        while pending:
            now = datetime.now()
            due = [r for r in pending if r.when <= now]
            for r in due:
                notify.send(
                    cfg.notify,
                    f"🚄 취소표 확인! [{r.trip_name}]",
                    f"{r.reason}\n지금 코레일+ 앱에서 좌석/취소표/예약대기를 확인하세요.",
                )
            pending = [r for r in pending if r.when > now]
            if not pending:
                break
            # 다음 알림까지 자되, 최대 30초 단위로 깨어 시계 변화를 반영합니다.
            wait = min(30.0, max(1.0, (pending[0].when - datetime.now()).total_seconds()))
            _time.sleep(wait)
    except KeyboardInterrupt:
        print("\n종료했습니다.")
        return 0

    print("모든 알림을 보냈습니다.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ktx_helper",
        description="KTX 취소표 예약대기 도우미 (합법: 알림 + 예약대기 안내 전용)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG,
        help=f"설정 파일 경로 (기본: {DEFAULT_CONFIG})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("guide", help="취소표/예약대기 전략 요약을 출력").set_defaults(func=cmd_guide)
    sub.add_parser("plan", help="여정과 추천 확인 시각을 출력").set_defaults(func=cmd_plan)

    p_ics = sub.add_parser("ics", help="추천 확인 시각을 캘린더(.ics)로 내보내기")
    p_ics.add_argument("-o", "--out", default="ktx_reminders.ics", help="출력 파일명")
    p_ics.set_defaults(func=cmd_ics)

    sub.add_parser("trains", help="공공데이터로 열차 시간표 조회(인증키 필요)").set_defaults(func=cmd_trains)
    sub.add_parser("test", help="알림 채널 테스트").set_defaults(func=cmd_test)
    sub.add_parser("remind", help="알림 스케줄러 실행(프로그램을 켜 둠)").set_defaults(func=cmd_remind)

    p_setup = sub.add_parser("setup-telegram", help="텔레그램 봇 설정(chat_id 자동 감지)")
    p_setup.add_argument("--bot-token", help="@BotFather 에서 발급받은 봇 토큰")
    p_setup.add_argument("--chat-id", help="여러 대화가 감지될 때 지정할 chat_id")
    p_setup.set_defaults(func=cmd_setup_telegram)

    p_win = sub.add_parser(
        "notify-window", help="리마인더 1회 발송(작업 스케줄러/GitHub Actions cron 용)"
    )
    p_win.add_argument("--title", help="알림 제목")
    p_win.add_argument("--message", help="알림 내용")
    p_win.add_argument("--until", help="이 날짜(YYYY-MM-DD) 이후로는 발송 안 함(출발일)")
    p_win.set_defaults(func=cmd_notify_window)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"\n⚠️  설정 오류: {exc}\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
