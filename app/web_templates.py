"""Jinja templates for the web page (kept in Python so the Docker image needs no extra files)."""

BASE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{% block title %}Stock Alerts{% endblock %}</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--text:#1d2330;--muted:#5f6b7a;--line:#dde2e8;--accent:#1f6feb;--accent-text:#fff;
--ok-bg:#e7f6ec;--ok:#1a7f37;--err-bg:#fdecec;--err:#c62828;--warn-bg:#fff6e0;--warn:#8a5a00;--badge:#eef1f5}
@media (prefers-color-scheme:dark){:root{--bg:#0f1318;--card:#171c23;--text:#e6e9ee;--muted:#9aa5b1;--line:#2a313b;
--accent:#4c8dff;--accent-text:#0b0e12;--ok-bg:#12291a;--ok:#5cd685;--err-bg:#331616;--err:#ff8a80;--warn-bg:#2e2510;
--warn:#f2c46d;--badge:#222a34}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--accent)}header{background:var(--card);border-bottom:1px solid var(--line)}
.wrap{max-width:960px;margin:0 auto;padding:0 16px}
nav{display:flex;flex-wrap:wrap;gap:4px 18px;align-items:center;padding:12px 0}
nav .brand{font-weight:700;margin-right:auto}nav a{text-decoration:none}nav form{margin:0}
main{padding:20px 0 60px}h1{font-size:1.4rem;margin:0 0 6px}h2{font-size:1.1rem;margin:0 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:0 0 16px}
.muted{color:var(--muted)}.small{font-size:.86rem}
.msg{padding:10px 12px;border-radius:8px;margin:0 0 12px}.msg.ok{background:var(--ok-bg);color:var(--ok)}
.msg.error{background:var(--err-bg);color:var(--err)}.msg.warn{background:var(--warn-bg);color:var(--warn)}
label{font-weight:600;font-size:.9rem;word-break:break-all}
input[type=text],input[type=password],input[type=number],select,textarea{width:100%;padding:8px 10px;border:1px solid var(--line);
border-radius:6px;background:var(--bg);color:var(--text);font:inherit}textarea{min-height:90px}
button,.btn{background:var(--accent);color:var(--accent-text);border:0;border-radius:6px;padding:8px 14px;font:inherit;
font-weight:600;cursor:pointer}button.secondary{background:var(--badge);color:var(--text)}button.danger{background:var(--err-bg);color:var(--err)}
button.link{background:none;color:var(--accent);padding:0;font-weight:400}
.row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:6px 16px;padding:10px 0;border-top:1px solid var(--line)}
.row:first-of-type{border-top:0}@media (max-width:640px){.row{grid-template-columns:1fr}}
.badge{display:inline-block;background:var(--badge);border-radius:999px;padding:0 8px;font-size:.78rem;font-weight:500;color:var(--muted)}
.badge.web{color:var(--ok)}.actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.sticky{position:sticky;bottom:0;background:var(--card);border-top:1px solid var(--line);padding:12px 16px;margin:0 -16px -16px;
border-radius:0 0 10px 10px}
.chips span{display:inline-block;background:var(--badge);border-radius:6px;padding:1px 8px;margin:2px 4px 2px 0}
details summary{cursor:pointer;font-weight:600}dl{margin:8px 0}dt{font-weight:600}dd{margin:0 0 8px;color:var(--muted)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media (max-width:640px){.grid2{grid-template-columns:1fr}}
.narrow{max-width:420px;margin:40px auto}.field{margin:0 0 12px}
</style></head><body>
<header><div class="wrap"><nav><span class="brand">Stock Alerts</span>
{% if user %}<a href="{{ url_for('index') }}">Settings</a><a href="{{ url_for('cvrs') }}">CVRs</a>
<a href="{{ url_for('password') }}">Password</a>
<form method="post" action="{{ url_for('logout') }}"><input type="hidden" name="csrf" value="{{ csrf }}">
<button class="link" type="submit">Log out</button></form>{% endif %}</nav></div></header>
<main class="wrap">
{% for cat, m in get_flashed_messages(with_categories=true) %}<div class="msg {{ cat }}">{{ m }}</div>{% endfor %}
{% block body %}{% endblock %}
</main></body></html>"""

SETUP = """{% extends "base.html" %}{% block title %}Set up · Stock Alerts{% endblock %}{% block body %}
<div class="card narrow"><h1>Create your login</h1>
<p class="muted small">Enter the setup code from the container logs (look for "First-time setup"), then choose the
username and password for this page.</p>
<form method="post"><input type="hidden" name="csrf" value="{{ csrf }}">
<div class="field"><label for="code">Setup code</label><input id="code" name="code" type="text" autocomplete="off" required></div>
<div class="field"><label for="username">Username</label><input id="username" name="username" type="text" autocomplete="username" required></div>
<div class="field"><label for="password">Password (8+ characters)</label><input id="password" name="password" type="password" autocomplete="new-password" required></div>
<div class="field"><label for="confirm">Repeat password</label><input id="confirm" name="confirm" type="password" autocomplete="new-password" required></div>
<button type="submit">Create login</button></form></div>{% endblock %}"""

LOGIN = """{% extends "base.html" %}{% block title %}Log in · Stock Alerts{% endblock %}{% block body %}
<div class="card narrow"><h1>Log in</h1>
<form method="post"><input type="hidden" name="csrf" value="{{ csrf }}">
<div class="field"><label for="username">Username</label><input id="username" name="username" type="text" autocomplete="username" required autofocus></div>
<div class="field"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required></div>
<button type="submit">Log in</button></form></div>{% endblock %}"""

PASSWORD = """{% extends "base.html" %}{% block title %}Password · Stock Alerts{% endblock %}{% block body %}
<div class="card narrow"><h1>Change password</h1>
<form method="post"><input type="hidden" name="csrf" value="{{ csrf }}">
<div class="field"><label for="current">Current password</label><input id="current" name="current" type="password" autocomplete="current-password" required></div>
<div class="field"><label for="password">New password (8+ characters)</label><input id="password" name="password" type="password" autocomplete="new-password" required></div>
<div class="field"><label for="confirm">Repeat new password</label><input id="confirm" name="confirm" type="password" autocomplete="new-password" required></div>
<button type="submit">Change password</button></form></div>{% endblock %}"""

SETTINGS = """{% extends "base.html" %}{% block title %}Settings · Stock Alerts{% endblock %}{% block body %}
<h1>Settings</h1>
<p class="muted">Values saved here override <code>.env</code>. Saving restarts the app (a few seconds) so changes take effect.</p>
{% for e in errors %}<div class="msg error">Setup needed: {{ e }}. Alerts are paused until it's fixed.</div>{% endfor %}
{% for w in warnings %}<div class="msg warn">{{ w }}</div>{% endfor %}
{% if env_count %}<div class="card"><div class="actions" style="justify-content:space-between">
<span>{{ env_count }} settings still come from <code>.env</code>. Copy them here so you can clear them out of the file.</span>
<form method="post" action="{{ url_for('import_env') }}"><input type="hidden" name="csrf" value="{{ csrf }}">
<button class="secondary" type="submit">Copy from .env</button></form></div></div>{% endif %}
<form method="post" action="{{ url_for('save_settings') }}"><input type="hidden" name="csrf" value="{{ csrf }}">
{% for group, items in groups.items() %}<div class="card"><h2>{{ group }}</h2>
{% for r in items %}<div class="row"><div><label for="{{ r.key }}">{{ r.key }}</label><br>
<span class="badge {{ r.source }}">{{ {'web': 'set here', 'env': 'from .env', 'default': 'default'}[r.source] }}</span>
{% if r.help %}<div class="muted small">{{ r.help }}</div>{% endif %}</div><div>
{% if r.type == 'bool' %}<select id="{{ r.key }}" name="{{ r.key }}">
{% for opt in ['true', 'false'] %}<option value="{{ opt }}" {% if (r.value or '').lower() in (['1','true','yes','on'] if opt == 'true' else ['0','false','no','off','']) %}selected{% endif %}>{{ opt }}</option>{% endfor %}</select>
{% elif r.choices %}<select id="{{ r.key }}" name="{{ r.key }}">{% for opt in r.choices %}<option {% if r.value == opt %}selected{% endif %}>{{ opt }}</option>{% endfor %}</select>
{% elif r.type == 'secret' %}<input id="{{ r.key }}" name="{{ r.key }}" type="password" autocomplete="off"
 placeholder="{{ 'Saved. Leave blank to keep it.' if r.is_set else 'Not set' }}">
{% else %}<input id="{{ r.key }}" name="{{ r.key }}" type="{{ 'number' if r.type in ('int','float') else 'text' }}"
 {% if r.type == 'float' %}step="any"{% endif %} value="{{ r.value }}" placeholder="{{ r.default }}">{% endif %}
{% if r.source == 'web' %}<label class="small muted" style="font-weight:400"><input type="checkbox" name="reset_{{ r.key }}">
 Reset to {{ '.env' if r.key in env_keys else 'default' }}</label>{% endif %}
</div></div>{% endfor %}</div>{% endfor %}
<div class="card sticky" style="position:sticky"><div class="actions"><button type="submit">Save and restart</button>
<span class="muted small">Blank secret fields keep their saved value.</span></div></div>
</form>{% endblock %}"""

RESTARTING = """{% extends "base.html" %}{% block title %}Restarting · Stock Alerts{% endblock %}{% block body %}
<meta http-equiv="refresh" content="8;url={{ url_for('index') }}">
<div class="card narrow"><h1>Saved</h1><p>Restarting with the new settings. This page reloads in a few seconds.</p>
<p class="muted small">Changed: {{ changed|join(', ') }}</p></div>{% endblock %}"""

CVRS = """{% extends "base.html" %}{% block title %}CVRs · Stock Alerts{% endblock %}{% block body %}
<h1>CVRs</h1>
<p class="muted">Add the ticker of the company that issued the CVR. The tool finds the CVR agreement at the SEC, who owes
the payments, and the assets it pays on. Alerts only fire for news about those assets or CVR payments.</p>
<div class="card"><form method="post" action="{{ url_for('cvr_add') }}" class="actions">
<input type="hidden" name="csrf" value="{{ csrf }}">
<input name="ticker" type="text" placeholder="Ticker, e.g. CYCN" style="max-width:220px" required {% if not ready %}disabled{% endif %}>
<button type="submit" {% if not ready %}disabled{% endif %}>Add CVR</button>
<span class="muted small">{{ 'The lookup reads SEC filings and can take a minute.' if ready else 'Finish the required settings first.' }}</span>
</form></div>
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
<form method="post" action="{{ url_for('cvr_edit', sym=x.sym) }}" style="margin-top:12px">
<input type="hidden" name="csrf" value="{{ csrf }}"><div class="grid2">
<div><label for="a-{{ x.sym }}">Assets (searched on their own)</label>
<textarea id="a-{{ x.sym }}" name="assets">{{ (x.assets or [])|join('\n') }}</textarea>
<div class="muted small">Drug or program names, one per line.</div></div>
<div><label for="c-{{ x.sym }}">Companies (searched together with "{{ x.name.split()[0] if x.name else '' }}")</label>
<textarea id="c-{{ x.sym }}" name="companies">{{ (x.companies or [])|join('\n') }}</textarea>
<div class="muted small">Buyers or licensees of the assets, one per line.</div></div></div>
<div class="actions" style="margin-top:10px"><button type="submit">Save terms</button></div></form>
<div class="actions" style="margin-top:10px">
<form method="post" action="{{ url_for('cvr_rediscover', sym=x.sym) }}"><input type="hidden" name="csrf" value="{{ csrf }}">
<button class="secondary" type="submit">Look up again</button></form>
<form method="post" action="{{ url_for('cvr_remove', sym=x.sym) }}" onsubmit="return confirm('Stop tracking {{ x.sym }}?')">
<input type="hidden" name="csrf" value="{{ csrf }}"><button class="danger" type="submit">Remove</button></form>
<span class="muted small">Added by {{ x.added_by }}</span></div>
</div>{% else %}<div class="card muted">No CVRs yet. Add one above, or use <code>/cvr add</code> in Discord.</div>{% endfor %}
{% endblock %}"""

TEMPLATES = {"base.html": BASE, "setup.html": SETUP, "login.html": LOGIN, "password.html": PASSWORD,
             "settings.html": SETTINGS, "restarting.html": RESTARTING, "cvrs.html": CVRS}
