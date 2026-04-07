from __future__ import annotations

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def _ensure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


_ensure_utf8()


_VIEW_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Job Search Viewer</title>
  <style>
    :root { color-scheme: light dark; }
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 16px; }
    .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    input { padding: 8px; min-width: 280px; }
    button { padding: 8px 12px; cursor: pointer; }
    table { border-collapse: collapse; width: 100%; margin-top: 12px; }
    th, td { border-bottom: 1px solid rgba(127,127,127,.35); padding: 8px; vertical-align: top; }
    th { text-align: left; position: sticky; top: 0; background: Canvas; }
    .muted { opacity: .75; }
    .pill { display: inline-block; padding: 2px 8px; border: 1px solid rgba(127,127,127,.35); border-radius: 999px; font-size: 12px; }
    .grid { display: grid; grid-template-columns: 1fr; gap: 8px; margin-top: 8px; }
    @media (min-width: 900px){ .grid { grid-template-columns: 1fr 1fr; } }
    /* Allow long URLs to wrap without breaking normal text (like job titles) per-letter. */
    a { overflow-wrap: anywhere; word-break: normal; }
    th.col-title, td.col-title { width: 40%; min-width: 380px; }
    td.col-title a { overflow-wrap: break-word; }
    /* Highlight sortable headers (Location/Remote/Published). */
    #thLocation, #thRemote, #thPublished { color: #ffcc00; }
  </style>
</head>
<body>
  <h2>Vacancies</h2>
  <div class="row">
    <label>Filter: <input id="q" placeholder="python, qa, devops..." /></label>
    <label><input id="onlyActive" type="checkbox" checked /> only active</label>
    <button onclick="load()">Refresh</button>
    <span class="muted" id="meta"></span>
  </div>

  <div class="grid">
    <div>
      <div class="muted">File: <span id="file"></span></div>
    </div>
    <div class="muted" style="text-align:right">API: <a href="/api/jobs" target="_blank">/api/jobs</a></div>
  </div>

  <table>
    <thead>
      <tr>
        <th class="col-title">Title</th>
        <th>Company</th>
        <th>Source</th>
        <th id="thLocation" style="cursor:pointer" title="Sort by location" onclick="setSort('location')">Location <span id="sortLocationIcon" class="muted"></span></th>
        <th id="thRemote" style="cursor:pointer" title="Sort by remote" onclick="setSort('remote')">Remote <span id="sortRemoteIcon" class="muted"></span></th>
        <th id="thPublished" style="cursor:pointer" title="Sort by published_at" onclick="setSort('published')">Published <span id="sortPublishedIcon" class="muted"></span></th>
        <th>Contacts</th>
      </tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>

<script>
let sortKey = 'published';
let sortDir = -1; // -1 desc, 1 asc

function setSort(key){
  if(sortKey === key){
    sortDir = sortDir * -1;
  } else {
    sortKey = key;
    sortDir = (key === 'location') ? 1 : -1;
  }
  renderSortIcons();
  load();
}

function renderSortIcons(){
  const icons = {
    published: document.getElementById('sortPublishedIcon'),
    remote: document.getElementById('sortRemoteIcon'),
    location: document.getElementById('sortLocationIcon'),
  };
  for(const k of Object.keys(icons)){
    const el = icons[k];
    if(!el) continue;
    // Show a neutral triangle for all sortable columns; filled triangle for active sort.
    el.textContent = (k === sortKey) ? (sortDir === 1 ? '\u25B2' : '\u25BC') : '\u25B3';
  }
}

function parseDateAny(s){
  if(!s) return 0;
  // ISO or YYYY-MM-DD
  const m1 = String(s).match(/(\d{4})-(\d{2})-(\d{2})/);
  if(m1){
    const d = new Date(`${m1[1]}-${m1[2]}-${m1[3]}T00:00:00Z`);
    const t = d.getTime();
    return Number.isFinite(t) ? t : 0;
  }
  const t = Date.parse(String(s));
  return Number.isFinite(t) ? t : 0;
}

async function load(){
  const res = await fetch('/api/jobs');
  const data = await res.json();
  const q = (document.getElementById('q').value || '').toLowerCase().split(',').map(s=>s.trim()).filter(Boolean);
  const onlyActive = document.getElementById('onlyActive').checked;

  document.getElementById('file').textContent = data.file || '';
  document.getElementById('meta').textContent = `Records: ${data.count}, Active: ${data.active}`;

  let jobs = data.jobs || [];
  if(onlyActive){ jobs = jobs.filter(j => j.is_active); }
  if(q.length){
    jobs = jobs.filter(j => {
      const hay = `${j.title||''}\n${j.company||''}\n${j.location||''}\n${(j.description||'').slice(0,500)}`.toLowerCase();
      return q.some(term => hay.includes(term));
    });
  }

  // sort
  jobs.sort((a,b)=>{
    const primary = compareBy(sortKey, a, b);
    if(primary !== 0) return primary * sortDir;
    // secondary: published desc
    const ta = parseDateAny(a.published_at);
    const tb = parseDateAny(b.published_at);
    if(ta === tb) return 0;
    return (ta < tb ? 1 : -1);
  });

  const tbody = document.getElementById('rows');
  tbody.innerHTML = '';

  for(const j of jobs){
    const tr = document.createElement('tr');
    const contacts = [];
    if(Array.isArray(j.emails) && j.emails.length){ contacts.push('email: ' + j.emails.join(', ')); }
    if(Array.isArray(j.phones) && j.phones.length){ contacts.push('tel: ' + j.phones.join(', ')); }

    tr.innerHTML = `
      <td class="col-title">
        <div><a href="${j.url}" target="_blank" rel="noreferrer">${escapeHtml(j.title||'(no title)')}</a></div>
      </td>
      <td>${escapeHtml(j.company||'')}</td>
      <td><span class="pill">${escapeHtml(j.source||'')}</span></td>
      <td>${escapeHtml(j.location||'')}</td>
      <td>${j.remote ? 'Yes' : 'No'}</td>
      <td>
        <div>${escapeHtml(j.published_at||'')}</div>
        <div class="muted">Seen: ${escapeHtml(j.first_seen_at||'')} → ${escapeHtml(j.last_seen_at||'')}</div>
      </td>
      <td>${escapeHtml(contacts.join('\n'))}</td>
    `;
    tbody.appendChild(tr);
  }
}

function escapeHtml(s){
  return String(s).replace(/[&<>\"']/g, (c)=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'
  }[c]));
}

function compareBy(key, a, b){
  if(key === 'published'){
    const ta = parseDateAny(a.published_at);
    const tb = parseDateAny(b.published_at);
    if(ta === tb) return 0;
    return (ta < tb ? -1 : 1);
  }
  if(key === 'remote'){
    const ra = a.remote ? 1 : 0;
    const rb = b.remote ? 1 : 0;
    if(ra === rb) return 0;
    return ra < rb ? -1 : 1;
  }
  if(key === 'location'){
    const la = (a.location || '').toString();
    const lb = (b.location || '').toString();
    return la.localeCompare(lb, undefined, { sensitivity: 'base' });
  }
  return 0;
}

renderSortIcons();

load();
</script>
</body>
</html>
"""


class _State:
    def __init__(self, json_path: Path):
        self.json_path = json_path

    def read_jobs(self) -> list[dict]:
        if not self.json_path.exists():
            return []
        try:
            data = json.loads(self.json_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []


def make_handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, content_type: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._send(200, "text/html; charset=utf-8", _VIEW_HTML.encode("utf-8"))
                return

            if parsed.path == "/api/jobs":
                jobs = state.read_jobs()
                payload = {
                    "file": str(state.json_path),
                    "count": len(jobs),
                    "active": sum(1 for j in jobs if isinstance(j, dict) and j.get("is_active")),
                    "jobs": jobs,
                }
                self._send(
                    200,
                    "application/json; charset=utf-8",
                    json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                )
                return

            if parsed.path == "/health":
                self._send(200, "text/plain; charset=utf-8", b"ok")
                return

            self._send(404, "text/plain; charset=utf-8", b"not found")

        def log_message(self, format, *args):  # noqa: A002
            return

    return Handler


def start_server(*, json_path: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    state = _State(json_path=json_path)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="job_search_server",
        description="Local server for viewing jobs JSON in a browser",
    )
    p.add_argument("--file", type=Path, default=Path("jobs_state.json"), help="JSON file to view")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), make_handler(_State(args.file)))
    try:
        print(f"Serving {args.file} on http://{args.host}:{args.port}/")
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
