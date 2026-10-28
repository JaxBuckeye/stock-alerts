"""Jinja templates for the web page (kept in Python so the Docker image needs no extra files).

Layout follows the Sonarr/Radarr pattern: top bar, left sidebar with sub-menus, a sticky page toolbar,
then the page. Dark theme, with the three-wizards logo as icon and a faint background watermark.
"""

BASE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{% block title %}Stock Alerts{% endblock %} · Stock Alerts</title>
<link rel="icon" type="image/svg+xml" href="{{ url_for('static', filename='logo.svg') }}">
<style>
:root{--bg:#1c1b22;--top:#26242e;--side:#22212a;--bar:#2a2833;--card:#28262f;--card2:#302d38;--line:#3a3744;
--text:#e8e6ef;--muted:#a29fb0;--faint:#77738a;--accent:#f5b83d;--accent-ink:#2a1d00;--violet:#8b6cff;
--ok:#37c27c;--err:#f0605a;--warn:#f0a83a;--ok-bg:rgba(55,194,124,.12);--err-bg:rgba(240,96,90,.12);
--warn-bg:rgba(240,168,58,.12);--hover:rgba(255,255,255,.05);--side-w:228px;--top-h:58px}
*{box-sizing:border-box}html{color-scheme:dark}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
code{background:var(--card2);padding:1px 6px;border-radius:4px;font-size:.92em}
.bg-logo{position:fixed;right:-60px;bottom:-60px;width:560px;height:560px;opacity:.05;pointer-events:none;z-index:0;
background:url("{{ url_for('static', filename='logo.svg') }}") no-repeat center/contain}
header.top{position:fixed;inset:0 0 auto 0;height:var(--top-h);background:var(--top);border-bottom:1px solid var(--line);
display:flex;align-items:center;gap:12px;padding:0 16px;z-index:30}
.brand{display:flex;align-items:center;gap:10px;color:var(--text);font-weight:700;font-size:17px;letter-spacing:.2px}
.brand:hover{text-decoration:none}.brand img{width:38px;height:38px;border-radius:9px}
.brand small{display:block;font-weight:500;font-size:11px;color:var(--muted);letter-spacing:.4px;margin-top:-2px}
.spacer{flex:1}.ver{color:var(--faint);font-size:12px}
.burger{display:none;color:var(--text);cursor:pointer;padding:6px}
aside.side{position:fixed;top:var(--top-h);bottom:0;left:0;width:var(--side-w);background:var(--side);
border-right:1px solid var(--line);overflow-y:auto;z-index:20;padding:10px 0 30px}
.nav a,.nav button{display:flex;align-items:center;gap:12px;width:100%;padding:10px 20px;color:var(--muted);
border:0;border-left:3px solid transparent;background:none;font:inherit;font-weight:600;cursor:pointer;text-align:left}
.nav a:hover,.nav button:hover{background:var(--hover);color:var(--text);text-decoration:none}
.nav a.active{color:var(--text);border-left-color:var(--accent);background:var(--hover)}
.nav a.sub{padding:6px 20px 6px 55px;font-weight:500;font-size:13px}.nav a.sub.active{color:var(--accent);background:none;border-left-color:transparent}
.nav svg{width:18px;height:18px;flex:none}.nav hr{border:0;border-top:1px solid var(--line);margin:10px 0}
main{position:relative;z-index:1;margin-left:var(--side-w);padding-top:var(--top-h);min-height:100vh}
.toolbar{position:sticky;top:var(--top-h);z-index:10;background:var(--bar);border-bottom:1px solid var(--line);
display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:10px 20px;min-height:56px}
.toolbar h1{font-size:17px;margin:0 12px 0 0}
.tbtn{display:inline-flex;align-items:center;gap:7px;background:none;border:0;color:var(--text);padding:7px 11px;
border-radius:6px;font:inherit;font-weight:600;cursor:pointer}.tbtn:hover{background:var(--hover);text-decoration:none}
.tbtn svg{width:17px;height:17px}.tbtn.primary{background:var(--accent);color:var(--accent-ink)}
.tbtn.primary:hover{filter:brightness(1.08)}
.page{padding:20px;max-width:1200px}
.msg{padding:10px 14px;border-radius:8px;margin:0 0 14px;border:1px solid transparent}
.msg.ok{background:var(--ok-bg);color:var(--ok);border-color:rgba(55,194,124,.3)}
.msg.error{background:var(--err-bg);color:var(--err);border-color:rgba(240,96,90,.3)}
.msg.warn{background:var(--warn-bg);color:var(--warn);border-color:rgba(240,168,58,.3)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin:0 0 16px}
.card h2{font-size:15px;margin:0 0 12px}.muted{color:var(--muted)}.small{font-size:12.5px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;color:var(--text);display:block}
a.tile:hover{border-color:var(--accent);text-decoration:none;background:var(--card2)}
.tile .t{font-weight:700;font-size:15px}.tile .d{color:var(--muted);font-size:13px;margin:4px 0 10px}
.stat .n{font-size:26px;font-weight:700}.stat .l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.6px}
.badge{display:inline-block;border-radius:999px;padding:1px 9px;font-size:11.5px;font-weight:600;background:var(--card2);color:var(--muted)}
.badge.web{color:var(--ok);background:var(--ok-bg)}.badge.env{color:var(--accent);background:rgba(245,184,61,.12)}
.badge.on{color:var(--ok);background:var(--ok-bg)}.badge.off{color:var(--faint)}
.badge.new{color:var(--accent-ink);background:var(--accent)}.badge.err{color:var(--err);background:var(--err-bg)}
input[type=text],input[type=password],input[type=number],select,textarea{width:100%;padding:8px 11px;border:1px solid var(--line);
border-radius:6px;background:#1a1920;color:var(--text);font:inherit}textarea{min-height:96px}
input:focus,select:focus,textarea:focus{outline:2px solid var(--violet);outline-offset:-1px}
button.btn{background:var(--accent);color:var(--accent-ink);border:0;border-radius:6px;padding:8px 16px;font:inherit;font-weight:700;cursor:pointer}
button.btn.secondary{background:var(--card2);color:var(--text)}button.btn.danger{background:var(--err-bg);color:var(--err)}
.form-row{display:grid;grid-template-columns:260px minmax(0,1fr);gap:8px 24px;padding:14px 0;border-top:1px solid var(--line)}
.form-row:first-child{border-top:0}.form-row label{font-weight:600;word-break:break-all}
.form-row .help{color:var(--muted);font-size:12.5px;margin-top:6px}
.actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
table.tbl{width:100%;border-collapse:collapse}table.tbl th{text-align:left;color:var(--muted);font-weight:600;font-size:12px;
text-transform:uppercase;letter-spacing:.5px;padding:8px 10px;border-bottom:1px solid var(--line)}
table.tbl td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}table.tbl tr:hover td{background:var(--hover)}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px}.chips span{display:inline-block;background:var(--card2);
border-radius:6px;padding:1px 8px;margin:2px 4px 2px 0}
details summary{cursor:pointer;font-weight:600}dl{margin:8px 0}dt{font-weight:600}dd{margin:0 0 8px;color:var(--muted)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.auth{max-width:400px;margin:70px auto;position:relative;z-index:1;padding:0 16px}
.auth .logo{display:block;width:110px;height:110px;margin:0 auto 14px;border-radius:24px;box-shadow:0 10px 40px rgba(139,108,255,.35)}
.auth h1{text-align:center;font-size:21px;margin:0 0 4px}.auth p.sub{text-align:center;color:var(--muted);margin:0 0 20px}
.field{margin:0 0 13px}.field label{display:block;font-weight:600;margin:0 0 5px}
@media (max-width:900px){.burger{display:block}aside.side{transform:translateX(-100%);transition:transform .2s}
#nav-toggle:checked ~ aside.side{transform:none;box-shadow:0 0 40px rgba(0,0,0,.6)}main{margin-left:0}
.form-row{grid-template-columns:1fr}.grid2{grid-template-columns:1fr}.page{padding:16px}.brand small{display:none}}
</style></head><body>
<div class="bg-logo" aria-hidden="true"></div>
{% if user %}
<input type="checkbox" id="nav-toggle" hidden>
<header class="top">
<label for="nav-toggle" class="burger" aria-label="Menu"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M3 12h18M3 18h18"/></svg></label>
<a class="brand" href="{{ url_for('index') }}"><img src="{{ url_for('static', filename='logo.svg') }}" alt="">
<span>Stock Alerts<small>THREE WIZARDS, ONE SPELL: PROFIT</small></span></a>
<span class="spacer"></span><a class="ver" href="{{ url_for('system_updates') }}">build {{ version }}</a>
</header>
{% set ic = {
 'activity': 'M22 12h-4l-3 9L9 3l-3 9H2',
 'list': 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
 'cvr': 'M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6',
 'settings': 'M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6',
 'system': 'M3 4h18v12H3zM8 20h8M12 16v4',
 'key': 'M15 7a4 4 0 1 1-3.9 4.9L3 20v-3l2-2v-2h2l2.1-2.1A4 4 0 0 1 15 7z',
 'logout': 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9'} %}
{% macro icon(n) %}<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="{{ ic[n] }}"/></svg>{% endmacro %}
<aside class="side"><nav class="nav">
<a href="{{ url_for('index') }}" class="{{ 'active' if endpoint == 'index' }}">{{ icon('activity') }}Activity</a>
<a href="{{ url_for('watchlist') }}" class="{{ 'active' if endpoint == 'watchlist' }}">{{ icon('list') }}Watchlist</a>
<a href="{{ url_for('cvrs') }}" class="{{ 'active' if endpoint == 'cvrs' }}">{{ icon('cvr') }}CVRs</a>
<a href="{{ url_for('settings_index') }}" class="{{ 'active' if endpoint and endpoint.startswith('settings') }}">{{ icon('settings') }}Settings</a>
{% if endpoint and endpoint.startswith('settings') %}{% for sl, name in sections %}
<a class="sub {{ 'active' if view_args.get('section') == sl }}" href="{{ url_for('settings_section', section=sl) }}">{{ name }}</a>{% endfor %}{% endif %}
<a href="{{ url_for('system_status') }}" class="{{ 'active' if endpoint and endpoint.startswith('system') }}">{{ icon('system') }}System</a>
{% if endpoint and endpoint.startswith('system') %}
<a class="sub {{ 'active' if endpoint == 'system_status' }}" href="{{ url_for('system_status') }}">Status</a>
<a class="sub {{ 'active' if endpoint == 'system_logs' }}" href="{{ url_for('system_logs') }}">Logs</a>
<a class="sub {{ 'active' if endpoint == 'system_updates' }}" href="{{ url_for('system_updates') }}">Updates</a>{% endif %}
<hr>
<a href="{{ url_for('password') }}" class="{{ 'active' if endpoint == 'password' }}">{{ icon('key') }}Password</a>
<form method="post" action="{{ url_for('logout') }}"><input type="hidden" name="csrf" value="{{ csrf }}">
<button type="submit">{{ icon('logout') }}Log out</button></form>
</nav></aside>
<main>
<div class="toolbar">{% block toolbar %}<h1>{{ self.title() }}</h1>{% endblock %}</div>
<div class="page">
{% for e in errors %}<div class="msg error">Setup needed: {{ e }}. Alerts are paused until it's fixed in <a href="{{ url_for('settings_index') }}">Settings</a>.</div>{% endfor %}
{% for cat, m in get_flashed_messages(with_categories=true) %}<div class="msg {{ cat }}">{{ m }}</div>{% endfor %}
{% block body %}{% endblock %}
</div></main>
{% else %}
<div class="auth">
<img class="logo" src="{{ url_for('static', filename='logo.svg') }}" alt="Three wizards casting a money spell">
{% for cat, m in get_flashed_messages(with_categories=true) %}<div class="msg {{ cat }}">{{ m }}</div>{% endfor %}
{% block auth %}{% endblock %}
</div>
{% endif %}
</body></html>"""

SETUP = """{% extends "base.html" %}{% block title %}Set up{% endblock %}{% block auth %}
<h1>Summon your login</h1><p class="sub">First visit: create the account for this page.</p>
<div class="card"><p class="muted small" style="margin-top:0">Enter the setup code from the container logs (look for
"First-time setup"), then choose a username and password.</p>
<form method="post"><input type="hidden" name="csrf" value="{{ csrf }}">
<div class="field"><label for="code">Setup code</label><input id="code" name="code" type="text" autocomplete="off" required></div>
<div class="field"><label for="username">Username</label><input id="username" name="username" type="text" autocomplete="username" required></div>
<div class="field"><label for="password">Password (8+ characters)</label><input id="password" name="password" type="password" autocomplete="new-password" required></div>
<div class="field"><label for="confirm">Repeat password</label><input id="confirm" name="confirm" type="password" autocomplete="new-password" required></div>
<button class="btn" type="submit" style="width:100%">Create login</button></form></div>{% endblock %}"""

LOGIN = """{% extends "base.html" %}{% block title %}Log in{% endblock %}{% block auth %}
<h1>Stock Alerts</h1><p class="sub">Three wizards, one spell: profit.</p>
<div class="card"><form method="post"><input type="hidden" name="csrf" value="{{ csrf }}">
<div class="field"><label for="username">Username</label><input id="username" name="username" type="text" autocomplete="username" required autofocus></div>
<div class="field"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required></div>
<button class="btn" type="submit" style="width:100%">Log in</button></form></div>{% endblock %}"""

PASSWORD = """{% extends "base.html" %}{% block title %}Password{% endblock %}{% block body %}
<div class="card" style="max-width:460px"><form method="post"><input type="hidden" name="csrf" value="{{ csrf }}">
<div class="field"><label for="current">Current password</label><input id="current" name="current" type="password" autocomplete="current-password" required></div>
<div class="field"><label for="password">New password (8+ characters)</label><input id="password" name="password" type="password" autocomplete="new-password" required></div>
<div class="field"><label for="confirm">Repeat new password</label><input id="confirm" name="confirm" type="password" autocomplete="new-password" required></div>
<button class="btn" type="submit">Change password</button></form></div>{% endblock %}"""

ACTIVITY = """{% extends "base.html" %}{% block title %}Activity{% endblock %}
{% block toolbar %}<h1>Activity</h1>
<button class="tbtn" id="refresh" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M23 4v6h-6M1 20v-6h6M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15"/></svg>Refresh</button>
<span class="muted small" id="live">Live · updates every 30s</span>{% endblock %}
{% block body %}
<style>
.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin:0 0 16px}
@media (max-width:640px){.stats{grid-template-columns:1fr 1fr}.stats .tile{padding:12px}.stat .n{font-size:22px}}
.filters{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0 0 14px}
.chip{border:1px solid var(--line);border-radius:999px;padding:3px 12px;color:var(--muted);font-weight:600;font-size:12.5px;background:var(--card)}
.chip:hover{color:var(--text);text-decoration:none;border-color:var(--faint)}.chip.on{color:var(--accent-ink);background:var(--accent);border-color:var(--accent)}
.chip i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:1px}
.feed{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.item{display:grid;grid-template-columns:4px 92px minmax(0,1fr) auto;gap:0 14px;padding:12px 16px 12px 0;border-top:1px solid var(--line)}
.item:first-child{border-top:0}.item:hover{background:var(--hover)}.item .bar{border-radius:0 3px 3px 0}
.item .k{font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;padding-top:2px}
.item .sym{display:inline-block;background:var(--card2);border-radius:5px;padding:0 7px;font-weight:700;font-size:12px;margin-right:8px;color:var(--text)}
.item .ttl{font-weight:600;color:var(--text)}.item a.ttl:hover{color:var(--accent)}
.item .m{color:var(--muted);font-size:13px;margin-top:3px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.item .meta{color:var(--faint);font-size:12px;margin-top:4px}.item time{color:var(--faint);font-size:12px;white-space:nowrap;padding-top:2px}
.item.fresh{animation:pop 2s ease-out}@keyframes pop{from{background:rgba(245,184,61,.18)}to{background:transparent}}
.empty{padding:40px 20px;text-align:center;color:var(--muted)}
@media (max-width:640px){.item{grid-template-columns:4px minmax(0,1fr) auto}.item .k{display:none}}
</style>
{% if dry_run %}<div class="msg warn">Dry run is on: alerts are logged here but not sent anywhere.</div>{% endif %}
<div class="stats">
<a class="tile stat" href="{{ url_for('watchlist') }}"><div class="n">{{ stats.tickers }}</div><div class="l">Tickers watched</div></a>
<a class="tile stat" href="{{ url_for('cvrs') }}"><div class="n">{{ stats.cvrs }}</div><div class="l">CVRs tracked</div></a>
<div class="tile stat"><div class="n">{{ stats.today }}</div><div class="l">Alerts, last 24h</div></div>
<a class="tile stat" href="{{ url_for('system_status') }}"><div class="l" style="margin-bottom:8px">Channels</div>
{% for name, on in stats.channels %}<span class="badge {{ 'on' if on else 'off' }}">{{ '●' if on else '○' }} {{ name }}</span> {% endfor %}</a>
</div>
<div class="filters">
<a class="chip {{ 'on' if not kind }}" href="{{ url_for('index', sym=sym or None) }}">All</a>
{% for k, label in kinds.items() %}<a class="chip {{ 'on' if kind == k }}" href="{{ url_for('index', kind=k, sym=sym or None) }}"><i style="background:{{ colors.get(k, '#888') }}"></i>{{ label }}</a>{% endfor %}
<form method="get" style="margin-left:auto;display:flex;gap:6px">{% if kind %}<input type="hidden" name="kind" value="{{ kind }}">{% endif %}
<input type="text" name="sym" value="{{ sym }}" placeholder="Ticker" style="width:110px;text-transform:uppercase">
<button class="btn secondary" type="submit">Filter</button>{% if sym %}<a class="chip" href="{{ url_for('index', kind=kind or None) }}">Clear {{ sym }}</a>{% endif %}</form>
</div>
<div class="feed" id="feed"></div>
<div class="actions" style="justify-content:center;margin-top:14px"><button class="btn secondary" id="more" type="button">Load older</button></div>
<script id="initial" type="application/json">{{ alerts|tojson }}</script>
<script>
(function(){
  const COLORS = {{ colors|tojson }}, LABELS = {{ kinds|tojson }};
  const KIND = {{ kind|tojson }}, SYM = {{ sym|tojson }};
  const feed = document.getElementById('feed'), more = document.getElementById('more');
  let items = JSON.parse(document.getElementById('initial').textContent);
  let maxId = items.length ? items[0].id : 0, minId = items.length ? items[items.length - 1].id : 0;
  function ago(ts){ const d = Math.max(0, Date.now()/1000 - ts);
    if (d < 60) return 'just now'; if (d < 3600) return Math.floor(d/60) + 'm ago';
    if (d < 86400) return Math.floor(d/3600) + 'h ago'; return Math.floor(d/86400) + 'd ago'; }
  function el(tag, cls, text){ const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function row(a, fresh){
    const r = el('div', 'item' + (fresh ? ' fresh' : '')), color = COLORS[a.kind] || '#888';
    const bar = el('div', 'bar'); bar.style.background = color; r.appendChild(bar);
    const k = el('div', 'k', LABELS[a.kind] || a.kind); k.style.color = color; r.appendChild(k);
    const body = el('div'); const head = el('div');
    if (a.sym) head.appendChild(el('span', 'sym', a.sym));
    let t;
    if (a.url && /^https?:\\/\\//.test(a.url)) { t = el('a', 'ttl', a.title); t.href = a.url; t.target = '_blank'; t.rel = 'noopener'; }
    else t = el('span', 'ttl', a.title);
    head.appendChild(t); body.appendChild(head);
    if (a.message && a.message !== a.title) body.appendChild(el('div', 'm', a.message));
    body.appendChild(el('div', 'meta', (a.priority >= 1 ? '⚡ urgent · ' : '') + 'Sent to ' + (a.delivered.join(', ') || 'nowhere')));
    r.appendChild(body);
    const tm = el('time', null, ago(a.ts)); tm.dataset.ts = a.ts; tm.title = new Date(a.ts * 1000).toLocaleString(); r.appendChild(tm);
    return r;
  }
  function render(){ feed.textContent = '';
    if (!items.length) { feed.appendChild(el('div', 'empty', 'No alerts yet. New ones appear here as the wizards find them.')); more.style.display = 'none'; return; }
    items.forEach(a => feed.appendChild(row(a))); more.style.display = items.length >= 100 ? '' : 'none'; }
  function q(extra){ const p = new URLSearchParams(extra); if (KIND) p.set('kind', KIND); if (SYM) p.set('sym', SYM); return '{{ url_for('api_alerts') }}?' + p; }
  async function poll(){
    try { const r = await fetch(q({after: maxId}), {credentials: 'same-origin'}); if (!r.ok) return;
      const fresh = await r.json(); if (!fresh.length) return;
      if (!items.length) feed.textContent = '';
      fresh.slice().reverse().forEach(a => feed.insertBefore(row(a, true), feed.firstChild));
      items = fresh.concat(items); maxId = fresh[0].id;
    } catch (e) {} }
  more.addEventListener('click', async () => {
    const r = await fetch(q({before: minId, limit: 100}), {credentials: 'same-origin'}); if (!r.ok) return;
    const older = await r.json(); older.forEach(a => feed.appendChild(row(a)));
    items = items.concat(older); if (older.length) minId = older[older.length - 1].id;
    if (older.length < 100) more.style.display = 'none'; });
  document.getElementById('refresh').addEventListener('click', poll);
  setInterval(poll, 30000);
  setInterval(() => document.querySelectorAll('#feed time').forEach(t => t.textContent = ago(+t.dataset.ts)), 60000);
  render();
})();
</script>
{% endblock %}"""

WATCHLIST = """{% extends "base.html" %}{% block title %}Watchlist{% endblock %}
{% block toolbar %}<h1>Watchlist</h1><span class="muted small">{{ rows|length }} tickers</span>{% endblock %}
{% block body %}
<p class="muted">{% if bot %}Add or remove tickers with <code>/watch add</code> and <code>/watch remove</code> in Discord.
{% else %}This list comes from the <a href="{{ url_for('settings_section', section='watchlist') }}">WATCHLIST setting</a>.{% endif %}
Newsroom and feed are found automatically; override one with <code>/watch site</code>.</p>
<div class="card" style="padding:6px 8px"><table class="tbl"><thead><tr><th>Ticker</th><th>Company</th><th>Newsroom</th><th>Feed</th><th></th></tr></thead><tbody>
{% for r in rows %}<tr><td><strong>{{ r.sym }}</strong></td><td>{{ r.name }}</td>
<td class="small">{% if r.news %}<a href="{{ r.news }}" target="_blank" rel="noopener">{{ r.news|replace('https://', '')|truncate(48, True) }}</a>{% elif r.homepage %}<span class="muted">homepage only</span>{% else %}<span class="muted">not found yet</span>{% endif %}
{% if r.manual %} <span class="badge">set by hand</span>{% endif %}</td>
<td class="small">{% if r.feed %}<a href="{{ r.feed }}" target="_blank" rel="noopener">RSS</a>{% else %}<span class="muted">none</span>{% endif %}</td>
<td>{% if r.blocked %}<span class="badge err" title="The site refuses automated access; press-wire search covers it">blocked</span>{% endif %}</td></tr>
{% else %}<tr><td colspan="5" class="muted" style="padding:30px;text-align:center">No tickers yet.</td></tr>{% endfor %}
</tbody></table></div>{% endblock %}"""

SETTINGS_INDEX = """{% extends "base.html" %}{% block title %}Settings{% endblock %}
{% block toolbar %}<h1>Settings</h1>
{% if env_count %}<form method="post" action="{{ url_for('import_env') }}"><input type="hidden" name="csrf" value="{{ csrf }}">
<button class="tbtn" type="submit"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>Copy from .env</button></form>{% endif %}
{% endblock %}
{% block body %}
{% for w in warnings %}<div class="msg warn">{{ w }}</div>{% endfor %}
<p class="muted">Values saved here override <code>.env</code>. Saving a section restarts the app (a few seconds) so the change takes effect.
{% if env_count %}{{ env_count }} settings still come from <code>.env</code>: <strong>Copy from .env</strong> stores them here so the file can be emptied.{% endif %}</p>
<div class="grid">{% for x in cards %}
<a class="tile" href="{{ url_for('settings_section', section=x.slug) }}"><div class="t">{{ x.name }}</div><div class="d">{{ x.info }}</div>
<span class="badge">{{ x.count }} settings</span>{% if x.web %} <span class="badge web">{{ x.web }} set here</span>{% endif %}
{% if x.env %} <span class="badge env">{{ x.env }} from .env</span>{% endif %}</a>{% endfor %}</div>{% endblock %}"""

SETTINGS = """{% extends "base.html" %}{% block title %}{{ group }}{% endblock %}
{% block toolbar %}<h1>Settings · {{ group }}</h1>
<button class="tbtn primary" type="submit" form="settings-form"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2zM17 21v-8H7v8M7 3v5h8"/></svg>Save changes</button>
<span class="muted small">Saving restarts the app. Blank secret fields keep their saved value.</span>{% endblock %}
{% block body %}
<p class="muted">{{ info }}</p>
<form id="settings-form" method="post" action="{{ url_for('save_settings', section=section) }}"><input type="hidden" name="csrf" value="{{ csrf }}">
<div class="card" style="padding:4px 20px">
{% for r in rows %}<div class="form-row"><div><label for="{{ r.key }}">{{ r.key }}</label><br>
<span class="badge {{ r.source }}">{{ {'web': 'set here', 'env': 'from .env', 'default': 'default'}[r.source] }}</span></div><div>
{% if r.type == 'bool' %}<select id="{{ r.key }}" name="{{ r.key }}">
{% for opt in ['true', 'false'] %}<option value="{{ opt }}" {% if (r.value or '').lower() in (['1','true','yes','on'] if opt == 'true' else ['0','false','no','off','']) %}selected{% endif %}>{{ 'Yes' if opt == 'true' else 'No' }}</option>{% endfor %}</select>
{% elif r.choices %}<select id="{{ r.key }}" name="{{ r.key }}">{% for opt in r.choices %}<option {% if r.value == opt %}selected{% endif %}>{{ opt }}</option>{% endfor %}</select>
{% elif r.type == 'secret' %}<input id="{{ r.key }}" name="{{ r.key }}" type="password" autocomplete="off"
 placeholder="{{ 'Saved. Leave blank to keep it.' if r.is_set else 'Not set' }}">
{% else %}<input id="{{ r.key }}" name="{{ r.key }}" type="{{ 'number' if r.type in ('int','float') else 'text' }}"
 {% if r.type == 'float' %}step="any"{% endif %} value="{{ r.value }}" placeholder="{{ r.default }}">{% endif %}
{% if r.help %}<div class="help">{{ r.help }}</div>{% endif %}
{% if r.source == 'web' %}<label class="small muted" style="font-weight:400;display:inline-flex;gap:6px;margin-top:6px">
<input type="checkbox" name="reset_{{ r.key }}"> Reset to {{ r.reset_to }}</label>{% endif %}
</div></div>{% endfor %}</div></form>{% endblock %}"""

RESTARTING = """{% extends "base.html" %}{% block title %}Restarting{% endblock %}{% block body %}
<meta http-equiv="refresh" content="8;url={{ back }}">
<div class="card" style="max-width:520px"><h2>Saved. The wizards are re-casting…</h2>
<p>Restarting with the new settings. This page reloads in a few seconds.</p>
<p class="muted small">Changed: {{ changed|join(', ') }}</p></div>{% endblock %}"""

CVRS = """{% extends "base.html" %}{% block title %}CVRs{% endblock %}
{% block toolbar %}<h1>CVRs</h1>
<form method="post" action="{{ url_for('cvr_add') }}" class="actions"><input type="hidden" name="csrf" value="{{ csrf }}">
<input name="ticker" type="text" placeholder="Ticker, e.g. CYCN" style="width:170px;text-transform:uppercase" required {% if not ready %}disabled{% endif %}>
<button class="tbtn primary" type="submit" {% if not ready %}disabled{% endif %}>+ Add CVR</button></form>
<span class="muted small">{{ 'The lookup reads SEC filings and can take a minute.' if ready else 'Finish the required settings first.' }}</span>{% endblock %}
{% block body %}
<p class="muted">Add the ticker of the company that issued the CVR. The tool finds the CVR agreement at the SEC, who owes
the payments, and the assets it pays on. Alerts only fire for news about those assets or CVR payments.</p>
{% for x in cvrs %}<div class="card" id="{{ x.sym }}">
<h2>{{ x.sym }} · {{ x.name }}{% if x.current_name %} <span class="muted small">(now {{ x.current_name }})</span>{% endif %}</h2>
{% for n in x.notes or [] %}<div class="msg warn">{{ n }}</div>{% endfor %}
{% if x.summary %}<p>{{ x.summary }}</p>{% endif %}
<p class="small">Pays out from: <strong>{{ x.obligor.name if x.obligor else 'unknown' }}</strong>
{% if x.obligor and x.obligor.ticker %} ({{ x.obligor.ticker }}){% endif %}
{% if x.agreement %} · <a href="{{ x.agreement.url }}" target="_blank" rel="noopener">CVR agreement</a> ({{ x.agreement.date }}){% endif %}
{% if x.prospectus %} · <a href="{{ x.prospectus.url }}" target="_blank" rel="noopener">{{ x.prospectus.form }}</a>{% endif %}</p>
{% if x.counterparties %}<p class="small chips">Counterparties: {% for cp in x.counterparties %}<span>{{ cp }}</span>{% endfor %}</p>{% endif %}
{% if x.key_terms %}<details><summary>Payment and milestone terms ({{ x.key_terms|length }})</summary><dl>
{% for t in x.key_terms %}<dt>{{ t.term }}</dt><dd>{{ t.text }}</dd>{% endfor %}</dl></details>{% endif %}
<form method="post" action="{{ url_for('cvr_edit', sym=x.sym) }}" style="margin-top:14px">
<input type="hidden" name="csrf" value="{{ csrf }}"><div class="grid2">
<div><label for="a-{{ x.sym }}"><strong>Assets</strong> <span class="muted small">searched on their own</span></label>
<textarea id="a-{{ x.sym }}" name="assets">{{ (x.assets or [])|join('\\n') }}</textarea>
<div class="muted small">Drug or program names, one per line.</div></div>
<div><label for="c-{{ x.sym }}"><strong>Companies</strong> <span class="muted small">searched together with "{{ x.name.split()[0] if x.name else '' }}"</span></label>
<textarea id="c-{{ x.sym }}" name="companies">{{ (x.companies or [])|join('\\n') }}</textarea>
<div class="muted small">Buyers or licensees of the assets, one per line.</div></div></div>
<div class="actions" style="margin-top:10px"><button class="btn" type="submit">Save terms</button></div></form>
<div class="actions" style="margin-top:10px">
<form method="post" action="{{ url_for('cvr_rediscover', sym=x.sym) }}"><input type="hidden" name="csrf" value="{{ csrf }}">
<button class="btn secondary" type="submit">Look up again</button></form>
<form method="post" action="{{ url_for('cvr_remove', sym=x.sym) }}" onsubmit="return confirm('Stop tracking {{ x.sym }}?')">
<input type="hidden" name="csrf" value="{{ csrf }}"><button class="btn danger" type="submit">Remove</button></form>
<span class="muted small">Added by {{ x.added_by }}</span></div>
</div>{% else %}<div class="card muted" style="text-align:center;padding:40px">No CVRs yet. Add one above, or use <code>/cvr add</code> in Discord.</div>{% endfor %}
{% endblock %}"""

STATUS = """{% extends "base.html" %}{% block title %}Status{% endblock %}
{% block toolbar %}<h1>System · Status</h1>{% endblock %}
{% block body %}
{% for w in warnings %}<div class="msg warn">{{ w }}</div>{% endfor %}
{% if health.status == 'ok' %}<div class="msg ok">🟢 Running normally. Every check is on schedule.</div>
{% elif health.status == 'warn' %}<div class="msg warn">🟡 Needs attention: {{ health.problems|join('; ') }}</div>{% endif %}
<div class="grid2">
<div class="card"><h2>About</h2><table class="tbl">{% for k, v in info %}<tr><td class="muted">{{ k }}</td><td>{{ v }}</td></tr>{% endfor %}</table></div>
<div class="card"><h2>Alert channels</h2><table class="tbl">{% for name, on in channels %}<tr><td>{{ name }}</td>
<td><span class="badge {{ 'on' if on else 'off' }}">{{ 'on' if on else 'off' }}</span></td></tr>{% endfor %}</table></div>
</div>
<div class="card"><h2>Checks</h2><table class="tbl"><thead><tr><th>Check</th><th>Every</th><th>Last ran</th><th>Status</th></tr></thead>
{% for j in jobs %}<tr><td>{{ j.name|capitalize }}</td><td>{{ j.every }}s</td><td class="muted">{{ j.last_run if j.on else '' }}</td>
<td>{% if not j.on %}<span class="badge off">off</span>{% elif errors %}<span class="badge off">paused</span>
{% elif j.error %}<span class="badge err" title="{{ j.error }}">failing</span>{% else %}<span class="badge on">running</span>{% endif %}</td></tr>{% endfor %}</table></div>
<div class="card"><h2>Blocked websites</h2>{% if blocked %}<table class="tbl"><thead><tr><th>Site</th><th>Answer</th><th>Retry in</th></tr></thead>
{% for host, code, mins in blocked %}<tr><td>{{ host }}</td><td>HTTP {{ code }}</td><td>{{ mins }} min</td></tr>{% endfor %}</table>
<p class="muted small">These sites refuse automated access. Press-wire search covers their releases.</p>
{% else %}<p class="muted" style="margin:0">None right now.</p>{% endif %}</div>{% endblock %}"""

LOGS = """{% extends "base.html" %}{% block title %}Logs{% endblock %}
{% block toolbar %}<h1>System · Logs</h1>
{% for lv in ['INFO', 'WARNING', 'ERROR'] %}<a class="tbtn {{ 'primary' if level == lv }}" href="{{ url_for('system_logs', level=lv) }}">{{ {'INFO': 'All', 'WARNING': 'Warnings', 'ERROR': 'Errors'}[lv] }}</a>{% endfor %}
<a class="tbtn" href="{{ url_for('system_logs', level=level) }}">Refresh</a>{% endblock %}
{% block body %}
<p class="muted small">The most recent log lines since the last restart (newest first). The full log is in <code>docker logs stock-alerts</code>.</p>
<div class="card" style="padding:6px 8px"><table class="tbl"><thead><tr><th>Time</th><th>Level</th><th>Source</th><th>Message</th></tr></thead>
{% for e in entries %}<tr><td class="mono" style="white-space:nowrap" title="{{ e.ts|when }}">{{ e.ts|ago }} ago</td>
<td><span class="badge {{ 'err' if e.level in ('ERROR', 'CRITICAL') else ('env' if e.level == 'WARNING' else '') }}">{{ e.level }}</span></td>
<td class="muted small">{{ e.name }}</td><td class="mono" style="white-space:pre-wrap;word-break:break-word">{{ e.msg|truncate(3000) }}</td></tr>
{% else %}<tr><td colspan="4" class="muted" style="padding:30px;text-align:center">Nothing logged at this level.</td></tr>{% endfor %}
</table></div>{% endblock %}"""

UPDATES = """{% extends "base.html" %}{% block title %}Updates{% endblock %}
{% block toolbar %}<h1>System · Updates</h1>
<a class="tbtn" href="{{ url_for('system_updates', check=1) }}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M23 4v6h-6M1 20v-6h6M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15"/></svg>Check for updates</a>{% endblock %}
{% block body %}
<div class="card"><h2>Installed</h2>
<p style="margin:0">Build <code>{{ current }}</code>{% if built %}, built {{ built }}{% endif %}.
{% if current == 'dev' %}<span class="muted">This is a local development build.</span>
{% elif newer %}<span class="badge new">{{ newer }} newer update{{ 's' if newer != 1 }}</span>
{% elif not err %}<span class="badge on">Up to date</span>{% endif %}</p>
{% if newer %}<p class="muted small" style="margin-bottom:0">To install: open the stack in Dockge and click <strong>Update</strong>
(or run <code>docker compose pull &amp;&amp; docker compose up -d</code>). Settings, watchlist and CVRs are kept.</p>{% endif %}
</div>
<div class="card"><h2>Latest on GitHub <span class="muted small">({{ repo }})</span></h2>
{% if err %}<div class="msg warn">Couldn't reach GitHub: {{ err }}</div>{% endif %}
<table class="tbl">{% for r in rows %}<tr><td class="mono" style="white-space:nowrap"><a href="https://github.com/{{ repo }}/commit/{{ r.sha }}" target="_blank" rel="noopener">{{ r.short }}</a></td>
<td class="muted small" style="white-space:nowrap">{{ r.date }}</td><td>{{ r.msg }}</td>
<td>{% if r.installed %}<span class="badge on">installed</span>{% elif r.new %}<span class="badge new">new</span>{% endif %}</td></tr>
{% else %}<tr><td class="muted">No information yet.</td></tr>{% endfor %}</table></div>
{% if changelog %}<div class="card"><h2>Changes in this build</h2><table class="tbl">
{% for sha, date, msg in changelog %}<tr><td class="mono">{{ sha }}</td><td class="muted small" style="white-space:nowrap">{{ date }}</td><td>{{ msg }}</td></tr>{% endfor %}
</table></div>{% endif %}{% endblock %}"""

TEMPLATES = {"base.html": BASE, "setup.html": SETUP, "login.html": LOGIN, "password.html": PASSWORD,
             "activity.html": ACTIVITY, "watchlist.html": WATCHLIST, "settings_index.html": SETTINGS_INDEX,
             "settings.html": SETTINGS, "restarting.html": RESTARTING, "cvrs.html": CVRS, "status.html": STATUS,
             "logs.html": LOGS, "updates.html": UPDATES}
