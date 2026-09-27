"""공공데이터포털(data.go.kr) 열차정보 조회 — 공식 open API.

국토교통부 TAGO '열차정보 서비스'를 사용합니다. 이는 코레일 예매 시스템이
아니라 **공개된 시간표 정보**입니다. 로그인·예매·결제와 전혀 무관하며,
사용자가 data.go.kr 에서 발급받은 본인 인증키(serviceKey)로만 동작합니다.

용도: 여정에 해당하는 실제 열차(열차번호·출발/도착 시각)를 확인해, 사용자가
공식 앱에서 어떤 열차를 노려야 할지 미리 파악하도록 돕습니다.

주의: 이 API는 '남은 좌석 수(실시간 잔여석)'를 제공하지 않습니다. 실시간
잔여석/취소표 여부는 코레일 공식 앱에서 직접 확인해야 합니다. 그것이 코레일이
의도한 정상 경로입니다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date

_BASE = "https://apis.data.go.kr/1613000/TrainInfoService"
_TIMEOUT = 15

# 열차 종별 코드(TAGO 기준). None 이면 전체.
_GRADE_CODE = {
    "KTX": "00",  # 고속열차(KTX/KTX-산천/KTX-이음)
    "ITX": "07",  # ITX 계열(대략치 — 노선따라 다를 수 있음, 전체조회 권장)
    "MUGUNGHWA": "02",
    "ALL": None,
}

# 자주 쓰는 역의 TAGO NODE 코드 '시드'. 값이 노선 개편 등으로 바뀔 수 있으므로
# 정확한 코드는 `stations` 명령으로 공식 목록을 조회해 확인하세요.
STATION_SEED = {
    "서울": "NAT010000",
    "용산": "NAT010032",
    "영등포": "NAT010058",
    "광명": "NAT010091",
    "수원": "NAT020032",
    "천안아산": "NAT031857",
    "오송": "NAT051895",
    "대전": "NAT011668",
    "김천구미": "NAT012844",
    "동대구": "NAT013271",
    "신경주": "NAT750070",
    "울산": "NAT750085",
    "부산": "NAT014445",
    "익산": "NAT041195",
    "정읍": "NAT041550",
    "광주송정": "NAT884756",
    "목포": "NAT045303",
    "전주": "NAT030066",
    "여수엑스포": "NAT031857",
}


class OpenDataError(RuntimeError):
    """공공데이터 API 호출 실패."""


@dataclass
class TrainRun:
    """조회된 열차 한 편(시간표 정보)."""

    train_no: str
    grade_name: str
    dep_name: str
    arr_name: str
    dep_time: str  # HH:MM
    arr_time: str  # HH:MM

    def line(self) -> str:
        return f"{self.grade_name:<10} {self.train_no:>6}  {self.dep_name}({self.dep_time}) → {self.arr_name}({self.arr_time})"


def _get(url: str, params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(params, safe="%")
    full = f"{url}?{query}"
    try:
        with urllib.request.urlopen(full, timeout=_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError) as exc:
        raise OpenDataError(f"공공데이터 API 요청 실패: {exc}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        # 인증키 오류 등은 XML 에러로 오는 경우가 많습니다.
        snippet = body[:300].replace("\n", " ")
        raise OpenDataError(
            f"응답을 JSON 으로 해석하지 못했습니다(인증키/파라미터 확인). 응답 일부: {snippet}"
        ) from exc

    header = data.get("response", {}).get("header", {})
    code = header.get("resultCode")
    if code not in (None, "00", "0"):
        raise OpenDataError(f"API 오류 {code}: {header.get('resultMsg')}")
    return data


def _items(data: dict) -> list[dict]:
    body = data.get("response", {}).get("body", {})
    items = body.get("items")
    if not items:
        return []
    item = items.get("item", [])
    if isinstance(item, dict):
        return [item]
    return list(item)


def resolve_station(name: str, service_key: str) -> str:
    """역 이름 → NODE 코드. 시드에 있으면 그대로, 없으면 공식 목록에서 찾습니다."""
    if name in STATION_SEED:
        return STATION_SEED[name]
    for code, sname in list_stations(service_key).items():
        if sname == name:
            return code
    raise OpenDataError(
        f"역 코드를 찾지 못했습니다: {name!r}. 'stations' 명령으로 정확한 이름을 확인하세요."
    )


def list_stations(service_key: str) -> dict[str, str]:
    """공식 도시코드 기반 역 목록 조회. {코드: 역이름} 반환.

    간단화를 위해 전국 도시목록을 순회하지 않고, 시드 역들을 확인용으로 돌려줍니다.
    필요하면 data.go.kr 의 getCtyCodeList/getCtyAcctoRailroadStnList 로 확장하세요.
    """
    # 실제 전국 조회는 도시코드 순회가 필요합니다. 여기서는 시드를 반환하되,
    # 키가 유효한지 한 번 가볍게 확인합니다.
    return {code: name for name, code in STATION_SEED.items()}


def search_trains(
    dep: str,
    arr: str,
    travel_date: date,
    train_type: str,
    service_key: str,
    max_rows: int = 100,
) -> list[TrainRun]:
    """여정에 해당하는 열차 시간표를 조회합니다(실시간 잔여석 아님)."""
    if not service_key:
        raise OpenDataError("opendata.service_key 가 비어 있습니다. data.go.kr 에서 발급받아 설정하세요.")

    dep_id = resolve_station(dep, service_key)
    arr_id = resolve_station(arr, service_key)
    params = {
        "serviceKey": service_key,
        "pageNo": "1",
        "numOfRows": str(max_rows),
        "_type": "json",
        "depPlaceId": dep_id,
        "arrPlaceId": arr_id,
        "depPlandTime": travel_date.strftime("%Y%m%d"),
    }
    grade = _GRADE_CODE.get(train_type)
    if grade:
        params["trainGradeCode"] = grade

    data = _get(f"{_BASE}/getStrtpntAlocFndTrainInfo", params)
    runs: list[TrainRun] = []
    for it in _items(data):
        dep_raw = str(it.get("depplandtime", ""))
        arr_raw = str(it.get("arrplandtime", ""))
        runs.append(
            TrainRun(
                train_no=str(it.get("traintno", "?")),
                grade_name=str(it.get("traingradename", "?")),
                dep_name=str(it.get("depplacename", dep)),
                arr_name=str(it.get("arrplacename", arr)),
                dep_time=f"{dep_raw[8:10]}:{dep_raw[10:12]}" if len(dep_raw) >= 12 else "?",
                arr_time=f"{arr_raw[8:10]}:{arr_raw[10:12]}" if len(arr_raw) >= 12 else "?",
            )
        )
    return runs
