"""로컬 설정 웹앱 — 메모장 대신 브라우저에서 여정을 편집합니다.

`python -m ktx_helper web` 로 실행하면 127.0.0.1(내 PC)에서만 열리는 설정 페이지가
뜹니다. 날짜·시간·역을 클릭으로 고르고 저장하면 ktx_config.json 이 자동 생성되며,
그 자리에서 텔레그램 테스트와 캘린더(.ics) 내려받기도 됩니다.

표준 라이브러리(http.server)만 사용합니다. 외부에 노출되지 않도록 로컬 주소에만
바인딩하고, 요청 Host 도 localhost 계열만 허용합니다(토큰이 폼에 있으므로).
"""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import notify
from .config import ConfigError, TRAIN_TYPES, build_config
from .ics import to_ics
from .opendata import STATION_SEED
from .windows import Reminder, default_reminders, upcoming

_ALLOWED_HOSTS = ("127.0.0.1", "localhost", "[::1]")

PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KTX 취소표 도우미 설정</title>
<style>
  :root { --bg:#f4f6fb; --card:#fff; --line:#e3e8f0; --ink:#1a2233; --sub:#5b6b86;
          --brand:#2f6bff; --brandink:#fff; --ok:#128a4c; --warn:#c0392b; --soft:#eef3ff; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family:"Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif; }
  .wrap { max-width:760px; margin:0 auto; padding:20px 16px 80px; }
  h1 { font-size:22px; margin:8px 0 2px; }
  .lead { color:var(--sub); font-size:14px; margin:0 0 18px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px;
          padding:18px; margin-bottom:16px; box-shadow:0 1px 3px rgba(20,30,60,.04); }
  .card h2 { font-size:16px; margin:0 0 12px; display:flex; align-items:center; gap:8px; }
  label { display:block; font-size:13px; color:var(--sub); margin:10px 0 4px; }
  input, select { width:100%; padding:10px 12px; border:1px solid var(--line);
          border-radius:9px; font-size:15px; background:#fff; color:var(--ink); }
  input:focus, select:focus { outline:2px solid var(--soft); border-color:var(--brand); }
  .row { display:flex; gap:12px; flex-wrap:wrap; }
  .row > div { flex:1; min-width:130px; }
  .trip { border:1px solid var(--line); border-radius:12px; padding:14px; margin-bottom:12px;
          position:relative; background:#fcfdff; }
  .trip .del { position:absolute; top:10px; right:10px; background:#fff; border:1px solid var(--line);
          color:var(--warn); border-radius:8px; padding:4px 10px; cursor:pointer; font-size:13px; }
  .btn { display:inline-flex; align-items:center; gap:6px; border:none; border-radius:10px;
          padding:11px 16px; font-size:15px; font-weight:600; cursor:pointer; }
  .btn.primary { background:var(--brand); color:var(--brandink); }
  .btn.ghost { background:#fff; border:1px solid var(--line); color:var(--ink); }
  .btn.add { background:var(--soft); color:var(--brand); border:1px dashed var(--brand); width:100%; justify-content:center; }
  .actions { display:flex; gap:10px; flex-wrap:wrap; margin-top:6px; }
  .hint { font-size:12.5px; color:var(--sub); margin-top:6px; line-height:1.5; }
  .chk { display:flex; align-items:center; gap:8px; margin-top:10px; }
  .chk input { width:auto; }
  .preview { font-size:13px; color:var(--sub); background:#f8faff; border:1px solid var(--line);
          border-radius:10px; padding:10px 12px; margin-top:10px; max-height:180px; overflow:auto; }
  .preview div { padding:2px 0; }
  #toast { position:fixed; left:50%; bottom:24px; transform:translateX(-50%);
          background:#12213f; color:#fff; padding:12px 18px; border-radius:10px; font-size:14px;
          opacity:0; transition:opacity .25s, transform .25s; pointer-events:none; max-width:90%; }
  #toast.show { opacity:1; transform:translateX(-50%) translateY(-4px); }
  #toast.err { background:var(--warn); }
  .tag { font-size:12px; background:var(--soft); color:var(--brand); border-radius:20px; padding:2px 10px; }
  .pwrow { display:flex; gap:8px; }
  .pwrow input { flex:1; }
  .pwrow button { white-space:nowrap; }
</style>
</head>
<body>
<div class="wrap">
  <h1>🚄 KTX 취소표 도우미 설정</h1>
  <p class="lead">메모장 대신 여기서 여정을 고르고 저장하세요. 저장하면 <code>ktx_config.json</code> 이 자동으로 갱신됩니다.</p>

  <div class="card">
    <h2>1. 여정 <span class="tag" id="tripCount">0개</span></h2>
    <div id="trips"></div>
    <button class="btn add" id="addTrip">+ 여정 추가</button>
  </div>

  <div class="card">
    <h2>2. 텔레그램 알림</h2>
    <div class="chk"><input type="checkbox" id="tgEnabled"><label for="tgEnabled" style="margin:0;color:var(--ink)">텔레그램으로 알림 받기</label></div>
    <label>봇 토큰 (@BotFather 발급)</label>
    <div class="pwrow">
      <input type="password" id="tgToken" placeholder="123456:ABC...">
      <button class="btn ghost" id="tgShow" type="button">보기</button>
    </div>
    <label>chat_id</label>
    <input type="text" id="tgChat" placeholder="숫자 (setup-telegram 또는 폰 브라우저로 확인)">
    <div class="actions" style="margin-top:12px">
      <button class="btn ghost" id="btnTest">📨 테스트 메시지 보내기</button>
    </div>
    <p class="hint">토큰/chat_id 를 모르면 비워도 됩니다. 나중에 <code>setup-telegram</code> 으로 채울 수 있어요.
       PC 네트워크에서 텔레그램이 막히면 GitHub Actions 방식을 쓰세요(README 6절).</p>
  </div>

  <div class="card">
    <h2>3. 알림 시점</h2>
    <label>출발 며칠 전부터 알림을 받을까요? <b id="dbLabel">3</b>일 전부터</label>
    <input type="range" id="daysBefore" min="0" max="14" value="3">
    <div class="chk"><input type="checkbox" id="useDefault" checked><label for="useDefault" style="margin:0;color:var(--ink)">취소표가 잘 나오는 기본 시간대 사용(자정 전후·새벽 등)</label></div>
    <div class="preview" id="preview">저장하면 다가오는 알림 시각이 여기 표시됩니다.</div>
  </div>

  <div class="actions">
    <button class="btn primary" id="btnSave">💾 저장</button>
    <button class="btn ghost" id="btnIcs">📅 캘린더(.ics) 내려받기</button>
  </div>
  <p class="hint">저장 후, 알림을 자동으로 받으려면: PC를 켜 두면 <code>remind</code>, PC를 꺼도 되게 하려면 GitHub Actions(README 6절).
     캘린더 파일은 폰 캘린더에 넣으면 프로그램 없이도 그 시각에 울립니다.</p>
</div>

<div id="toast"></div>

<script>
let STATE = { stations: [], trainTypes: {}, config: null };

function el(tag, attrs, children) {
  const e = document.createElement(tag);
  for (const k in (attrs||{})) {
    if (k === 'class') e.className = attrs[k];
    else if (k === 'html') e.innerHTML = attrs[k];
    else e.setAttribute(k, attrs[k]);
  }
  (children||[]).forEach(c => e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c));
  return e;
}

function stationOptions(selected) {
  const dl = STATE.stations.map(s => `<option value="${s}">`).join('');
  return dl;
}

function tripCard(t) {
  t = t || { name:'', dep:'서울', arr:'부산', date:'', time_from:'08:00', time_to:'12:00', train_type:'KTX', passengers:1 };
  const wrap = el('div', { class:'trip' });
  const typeOpts = Object.keys(STATE.trainTypes).map(k =>
     `<option value="${k}" ${k===t.train_type?'selected':''}>${STATE.trainTypes[k]}</option>`).join('');
  wrap.innerHTML = `
    <button class="del" type="button">삭제</button>
    <label>여정 이름(선택)</label>
    <input class="f-name" placeholder="예: 서울→부산 추석" value="${t.name||''}">
    <div class="row">
      <div><label>출발역</label><input class="f-dep" list="stns" value="${t.dep||''}"></div>
      <div><label>도착역</label><input class="f-arr" list="stns" value="${t.arr||''}"></div>
    </div>
    <div class="row">
      <div><label>날짜</label><input class="f-date" type="date" value="${t.date||''}"></div>
      <div><label>인원</label><input class="f-psg" type="number" min="1" max="9" value="${t.passengers||1}"></div>
    </div>
    <div class="row">
      <div><label>시작 시간</label><input class="f-tf" type="time" value="${t.time_from||'00:00'}"></div>
      <div><label>종료 시간</label><input class="f-tt" type="time" value="${t.time_to||'23:59'}"></div>
      <div><label>열차 종류</label><select class="f-type">${typeOpts}</select></div>
    </div>`;
  wrap.querySelector('.del').onclick = () => { wrap.remove(); refreshCount(); };
  return wrap;
}

function refreshCount() {
  document.getElementById('tripCount').textContent = document.querySelectorAll('.trip').length + '개';
}

function collect() {
  const trips = [...document.querySelectorAll('.trip')].map(w => ({
    name: w.querySelector('.f-name').value.trim(),
    dep: w.querySelector('.f-dep').value.trim(),
    arr: w.querySelector('.f-arr').value.trim(),
    date: w.querySelector('.f-date').value,
    time_from: w.querySelector('.f-tf').value || '00:00',
    time_to: w.querySelector('.f-tt').value || '23:59',
    train_type: w.querySelector('.f-type').value,
    passengers: parseInt(w.querySelector('.f-psg').value || '1', 10),
  }));
  const base = STATE.config || {};
  return {
    trips,
    reminders: {
      use_default_windows: document.getElementById('useDefault').checked,
      days_before: parseInt(document.getElementById('daysBefore').value, 10),
      extra_times: (base.reminders && base.reminders.extra_times) || [],
    },
    notify: {
      desktop: (base.notify && base.notify.desktop) !== false,
      telegram: {
        enabled: document.getElementById('tgEnabled').checked,
        bot_token: document.getElementById('tgToken').value.trim(),
        chat_id: document.getElementById('tgChat').value.trim(),
      },
      webhook: (base.notify && base.notify.webhook) || { enabled:false, url:'' },
    },
    opendata: base.opendata || { service_key:'' },
  };
}

function toast(msg, isErr) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'show' + (isErr ? ' err' : '');
  setTimeout(() => { t.className = ''; }, isErr ? 5000 : 2800);
}

async function save() {
  const data = collect();
  const r = await fetch('/api/save', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) });
  const j = await r.json();
  if (j.ok) { toast('✅ 저장했습니다'); STATE.config = data; loadPreview(); }
  else toast('⚠️ ' + j.error, true);
}

async function loadPreview() {
  const r = await fetch('/api/preview');
  const j = await r.json();
  const box = document.getElementById('preview');
  if (!j.ok) { box.textContent = j.error || '먼저 저장하세요.'; return; }
  if (!j.reminders.length) { box.textContent = '다가오는 알림이 없습니다(여정 날짜 확인).'; return; }
  box.innerHTML = '';
  j.reminders.forEach(line => box.appendChild(el('div', {}, [line])));
}

async function testTg() {
  const tg = collect().notify.telegram;
  if (!tg.bot_token || !tg.chat_id) { toast('봇 토큰과 chat_id 를 먼저 입력하세요', true); return; }
  toast('전송 중...');
  const r = await fetch('/api/test', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(tg) });
  const j = await r.json();
  toast(j.ok ? '📨 보냈습니다. 폰을 확인하세요!' : '⚠️ ' + (j.error||'전송 실패'), !j.ok);
}

async function init() {
  const r = await fetch('/api/state');
  STATE = await r.json();
  document.body.insertAdjacentHTML('beforeend', `<datalist id="stns">${stationOptions()}</datalist>`);
  const c = STATE.config || {};
  const trips = (c.trips && c.trips.length) ? c.trips : [null];
  const host = document.getElementById('trips');
  trips.forEach(t => host.appendChild(tripCard(t)));
  refreshCount();
  if (c.reminders) {
    document.getElementById('daysBefore').value = c.reminders.days_before ?? 3;
    document.getElementById('useDefault').checked = c.reminders.use_default_windows !== false;
  }
  document.getElementById('dbLabel').textContent = document.getElementById('daysBefore').value;
  const tg = (c.notify && c.notify.telegram) || {};
  document.getElementById('tgEnabled').checked = !!tg.enabled;
  document.getElementById('tgToken').value = tg.bot_token || '';
  document.getElementById('tgChat').value = tg.chat_id || '';
  loadPreview();
}

document.getElementById('addTrip').onclick = () => { document.getElementById('trips').appendChild(tripCard()); refreshCount(); };
document.getElementById('btnSave').onclick = save;
document.getElementById('btnTest').onclick = testTg;
document.getElementById('btnIcs').onclick = () => { window.location = '/api/ics'; };
document.getElementById('daysBefore').oninput = e => { document.getElementById('dbLabel').textContent = e.target.value; };
document.getElementById('tgShow').onclick = () => {
  const i = document.getElementById('tgToken');
  i.type = i.type === 'password' ? 'text' : 'password';
};
init();
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    config_path = "ktx_config.json"

    # 로그 소음 억제
    def log_message(self, *args):  # noqa: D401
        pass

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost") or f"[{host}]" in _ALLOWED_HOSTS

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _load_raw(self) -> dict:
        p = Path(self.config_path)
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def do_GET(self):
        if not self._host_ok():
            self._json({"error": "forbidden"}, 403)
            return
        path = urlparse(self.path).path
        if path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/state":
            self._json({
                "stations": list(STATION_SEED.keys()),
                "trainTypes": TRAIN_TYPES,
                "config": self._load_raw() or None,
            })
        elif path == "/api/preview":
            self._preview()
        elif path == "/api/ics":
            self._ics()
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._host_ok():
            self._json({"error": "forbidden"}, 403)
            return
        path = urlparse(self.path).path
        try:
            body = self._read_body()
        except (json.JSONDecodeError, ValueError) as exc:
            self._json({"ok": False, "error": f"요청 파싱 실패: {exc}"}, 400)
            return
        if path == "/api/save":
            self._save(body)
        elif path == "/api/test":
            self._test(body)
        else:
            self._json({"error": "not found"}, 404)

    def _save(self, data: dict):
        try:
            build_config(data)  # 검증
        except ConfigError as exc:
            self._json({"ok": False, "error": str(exc)})
            return
        try:
            Path(self.config_path).write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            self._json({"ok": False, "error": f"파일 저장 실패: {exc}"})
            return
        self._json({"ok": True})

    def _test(self, tg: dict):
        token, chat = str(tg.get("bot_token", "")).strip(), str(tg.get("chat_id", "")).strip()
        if not token or not chat:
            self._json({"ok": False, "error": "봇 토큰과 chat_id 가 필요합니다"})
            return
        ok, detail = notify.telegram_send_result(token, chat, "KTX 도우미", "설정 화면에서 보낸 테스트입니다. 🚄")
        if ok:
            self._json({"ok": True, "error": None})
            return
        low = detail.lower()
        hint = ""
        if "chat not found" in low or detail.startswith("400"):
            hint = " → chat_id 를 확인하세요. 순수 숫자여야 하고, 봇에게 먼저 아무 메시지나 보낸 뒤라야 합니다."
        elif "blocked" in low or detail.startswith("403"):
            hint = " → 봇 대화창을 열어 먼저 메시지를 보내고(차단 해제), 다시 시도하세요."
        elif detail.startswith("401") or "unauthorized" in low:
            hint = " → 봇 토큰이 올바른지 확인하세요(폐기된 토큰일 수 있음)."
        self._json({"ok": False, "error": f"전송 실패: {detail}{hint}"})

    def _reminders(self) -> list[Reminder]:
        cfg = build_config(self._load_raw())
        out: list[Reminder] = []
        if cfg.reminders.use_default_windows:
            for trip in cfg.trips:
                out += default_reminders(
                    trip.name, trip.travel_date, cfg.reminders.days_before, trip.time_from
                )
        for extra in cfg.reminders.extra_times:
            out.append(Reminder(when=extra, trip_name="사용자 지정", reason="직접 지정한 확인 시각"))
        return sorted(out, key=lambda r: r.when)

    def _preview(self):
        try:
            reminders = upcoming(self._reminders())
        except ConfigError as exc:
            self._json({"ok": False, "error": str(exc)})
            return
        self._json({"ok": True, "reminders": [r.line() for r in reminders[:30]]})

    def _ics(self):
        try:
            reminders = upcoming(self._reminders())
        except ConfigError as exc:
            self._json({"ok": False, "error": str(exc)}, 400)
            return
        body = to_ics(reminders).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/calendar; charset=utf-8")
        self.send_header("Content-Disposition", "attachment; filename=ktx_reminders.ics")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(config_path: str = "ktx_config.json", port: int = 8777, open_browser: bool = True) -> int:
    """로컬 설정 웹앱을 실행합니다. Ctrl+C 로 종료."""
    _Handler.config_path = config_path
    url = f"http://127.0.0.1:{port}/"
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"🌐 설정 화면을 열었습니다: {url}")
    print("   브라우저가 자동으로 안 열리면 위 주소를 직접 여세요. 종료: Ctrl+C")
    if open_browser:
        try:
            webbrowser.open(url)
        except OSError:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n설정 화면을 종료했습니다.")
    finally:
        server.server_close()
    return 0
