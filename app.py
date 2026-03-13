"""
app.py — SPF Media Monitor Dashboard
Flask web app hosted on Render, reads from PostgreSQL.
Password protected. Shows flagged posts in real time.
"""

import os
from datetime import datetime
from functools import wraps

from flask import Flask, render_template_string, request, redirect, session, url_for
import database

app = Flask(__name__)
app.secret_key = os.getenv("DASHBOARD_SECRET", "spf-monitor-secret-change-me")

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "spfmonitor2026")

# ── Auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        if request.form.get("password") == DASHBOARD_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = "Incorrect password"
    return render_template_string(LOGIN_HTML, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    posts  = database.get_flagged_posts(limit=100)
    stats  = database.get_stats()
    rules  = database.get_rules()
    source = request.args.get("source", "all")
    search = request.args.get("search", "").lower()

    if source != "all":
        posts = [p for p in posts if p["source"] == source]
    if search:
        posts = [p for p in posts if search in (p.get("content") or "").lower()
                 or search in (p.get("url") or "").lower()]

    return render_template_string(
        DASHBOARD_HTML,
        posts=posts, stats=stats, rules=rules,
        source=source, search=search,
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    )


# ── Templates ─────────────────────────────────────────────────────────────────

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>SPF Monitor — Login</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Arial, sans-serif; background: #1a252f; display: flex;
           align-items: center; justify-content: center; min-height: 100vh; }
    .box { background: white; padding: 40px; border-radius: 8px; width: 340px; }
    h2 { color: #1a252f; margin-bottom: 8px; font-size: 20px; }
    p  { color: #888; font-size: 13px; margin-bottom: 24px; }
    input { width: 100%; padding: 10px 14px; border: 1px solid #ddd;
            border-radius: 4px; font-size: 14px; margin-bottom: 12px; }
    button { width: 100%; background: #1a252f; color: white; padding: 10px;
             border: none; border-radius: 4px; font-size: 14px; cursor: pointer; }
    .error { color: #c0392b; font-size: 13px; margin-bottom: 12px; }
  </style>
</head>
<body>
  <div class="box">
    <h2>SPF Media Monitor</h2>
    <p>Enter password to access the dashboard</p>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST">
      <input type="password" name="password" placeholder="Password" autofocus>
      <button type="submit">Login</button>
    </form>
  </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>SPF Media Monitor</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Arial, sans-serif; background: #f4f6f8; color: #333; }

    .header { background: #1a252f; color: white; padding: 14px 24px;
              display: flex; align-items: center; justify-content: space-between; }
    .header h1 { font-size: 18px; }
    .header .meta { font-size: 12px; color: #aaa; }
    .header a { color: #aaa; font-size: 12px; text-decoration: none; }

    .stats { display: flex; gap: 16px; padding: 20px 24px; flex-wrap: wrap; }
    .stat  { background: white; border-radius: 6px; padding: 16px 20px;
             flex: 1; min-width: 120px; border: 1px solid #e0e0e0; }
    .stat .num   { font-size: 28px; font-weight: bold; color: #1a252f; }
    .stat .label { font-size: 12px; color: #888; margin-top: 4px; }

    .controls { padding: 0 24px 16px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
    .controls form { display: flex; gap: 8px; flex-wrap: wrap; }
    input[type=text] { padding: 7px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; width: 220px; }
    select { padding: 7px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; }
    button[type=submit] { padding: 7px 16px; background: #2980b9; color: white;
                          border: none; border-radius: 4px; font-size: 13px; cursor: pointer; }
    .refresh { font-size: 12px; color: #888; margin-left: auto; }

    .posts { padding: 0 24px 24px; }
    .post  { background: white; border-radius: 6px; border: 1px solid #e0e0e0;
             margin-bottom: 12px; overflow: hidden; }
    .post-header { padding: 12px 16px; display: flex; align-items: center; gap: 10px;
                   border-bottom: 1px solid #f0f0f0; }
    .badge { font-size: 11px; color: white; padding: 2px 8px; border-radius: 3px; font-weight: bold; }
    .badge.high   { background: #c0392b; }
    .badge.medium { background: e67e22; background-color: #e67e22; }
    .badge.low    { background: #27ae60; }
    .post-source { font-size: 12px; color: #888; }
    .post-time   { font-size: 12px; color: #aaa; margin-left: auto; }

    .post-body    { padding: 12px 16px; }
    .post-summary { font-size: 14px; font-weight: bold; color: #1a252f; margin-bottom: 10px; }
    .post-caption { background: #f8f9fa; border: 1px solid #e9ecef; padding: 10px 14px;
                    border-radius: 4px; font-size: 12px; color: #333; line-height: 1.6;
                    margin-bottom: 8px; max-height: 120px; overflow-y: auto; }
    .post-visual  { background: #fdf2f2; border-left: 3px solid #e67e22;
                    padding: 8px 12px; font-size: 12px; color: #555; margin-bottom: 8px; }
    .post-footer  { padding: 10px 16px; border-top: 1px solid #f0f0f0;
                    display: flex; align-items: center; gap: 12px; }
    .post-footer a { font-size: 12px; color: #2980b9; text-decoration: none; }
    .fb-count { font-size: 11px; color: #aaa; margin-left: auto; }
    .fb-correct   { color: #27ae60 !important; font-weight: bold; }
    .fb-incorrect { color: #c0392b !important; font-weight: bold; }

    .no-posts { text-align: center; padding: 60px; color: #aaa; font-size: 14px; }

    .rules-panel { margin: 0 24px 24px; background: white; border-radius: 6px;
                   border: 1px solid #e0e0e0; }
    .rules-panel h3 { padding: 12px 16px; font-size: 14px; border-bottom: 1px solid #f0f0f0; color: #1a252f; }
    .rule-row { padding: 8px 16px; font-size: 12px; border-bottom: 1px solid #f9f9f9;
                display: flex; gap: 12px; }
    .rule-type { width: 50px; font-weight: bold; }
    .rule-type.flag   { color: #e67e22; }
    .rule-type.ignore { color: #888; }
    .rule-pattern { color: #333; font-family: monospace; }
    .rule-reason  { color: #aaa; }

    @media (max-width: 600px) {
      .stats { padding: 12px; }
      .posts, .controls, .rules-panel { padding-left: 12px; padding-right: 12px; }
    }
  </style>
  <meta http-equiv="refresh" content="300">
</head>
<body>

<div class="header">
  <div>
    <h1>SPF Media Monitor</h1>
    <div class="meta">Last updated: {{ now }}</div>
  </div>
  <a href="/logout">Logout</a>
</div>

<div class="stats">
  <div class="stat">
    <div class="num">{{ stats.get('flagged', 0) }}</div>
    <div class="label">Posts Flagged</div>
  </div>
  <div class="stat">
    <div class="num">{{ (stats.get('flagged', 0) or 0) + (stats.get('scanned', 0) or 0) }}</div>
    <div class="label">Total Scanned</div>
  </div>
  <div class="stat">
    <div class="num">{{ stats.get('instagram', 0) }}</div>
    <div class="label">Instagram Posts</div>
  </div>
  <div class="stat">
    <div class="num">{{ stats.get('news', 0) }}</div>
    <div class="label">News Articles</div>
  </div>
  <div class="stat">
    <div class="num">{{ stats.get('learned_rules', 0) }}</div>
    <div class="label">Rules Learned</div>
  </div>
</div>

<div class="controls">
  <form method="GET">
    <select name="source" onchange="this.form.submit()">
      <option value="all" {% if source=='all' %}selected{% endif %}>All sources</option>
      <option value="instagram" {% if source=='instagram' %}selected{% endif %}>Instagram</option>
      <option value="straits_times" {% if source=='straits_times' %}selected{% endif %}>Straits Times</option>
      <option value="zaobao" {% if source=='zaobao' %}selected{% endif %}>Zaobao</option>
    </select>
    <input type="text" name="search" placeholder="Search posts..." value="{{ search }}">
    <button type="submit">Search</button>
  </form>
  <span class="refresh">Auto-refreshes every 5 minutes</span>
</div>

<div class="posts">
  {% if posts %}
    {% for post in posts %}
    {% set content = post.get('content','') %}
    {% set visual = '' %}
    {% set caption = '' %}
    {% for line in content.split('\n') %}
      {% if line.startswith('[VISUAL') %}
        {% set visual = line.strip('[]') %}
      {% elif line.startswith('Caption:') %}
        {% set caption = line[8:] %}
      {% endif %}
    {% endfor %}
    {% if not caption and not visual %}
      {% set caption = content %}
    {% endif %}

    <div class="post">
      <div class="post-header">
        <span class="badge {{ post.get('severity', post.get('source','')) }}
              {% if 'high' in content.lower() %} high
              {% elif 'medium' in content.lower() %} medium
              {% else %} low {% endif %}">
          {% if '[VISUAL — HIGH' in content %}HIGH
          {% elif '[VISUAL — MEDIUM' in content %}MEDIUM
          {% else %}FLAGGED{% endif %}
        </span>
        <span class="post-source">
          {% if post['source'] == 'instagram' %}📱 @{{ post.get('author','').replace('@','') }}
          {% elif post['source'] == 'straits_times' %}📰 Straits Times
          {% elif post['source'] == 'zaobao' %}📰 Zaobao
          {% else %}{{ post['source'] }}{% endif %}
        </span>
        <span class="post-time">{{ post.get('created_at','')[:16] if post.get('created_at') else '' }}</span>
      </div>

      <div class="post-body">
        {% if caption %}
        <div class="post-caption">{{ caption[:500] }}{% if caption|length > 500 %}...{% endif %}</div>
        {% endif %}
        {% if visual %}
        <div class="post-visual">🎥 {{ visual[:200] }}</div>
        {% endif %}
      </div>

      <div class="post-footer">
        <a href="{{ post['url'] }}" target="_blank">View original →</a>
        {% if post.get('correct_count', 0) %}
          <span class="fb-count fb-correct">✓ {{ post['correct_count'] }} correct</span>
        {% endif %}
        {% if post.get('incorrect_count', 0) %}
          <span class="fb-count fb-incorrect">✗ {{ post['incorrect_count'] }} not relevant</span>
        {% endif %}
      </div>
    </div>
    {% endfor %}
  {% else %}
    <div class="no-posts">No flagged posts yet. The bot will populate this as it scans.</div>
  {% endif %}
</div>

{% if rules %}
<div class="rules-panel">
  <h3>🧠 Learned Rules ({{ rules|length }})</h3>
  {% for rule in rules %}
  <div class="rule-row">
    <span class="rule-type {{ rule['rule_type'] }}">{{ rule['rule_type'].upper() }}</span>
    <span class="rule-pattern">"{{ rule['pattern'] }}"</span>
    <span class="rule-reason">{{ rule.get('reason','') }}</span>
  </div>
  {% endfor %}
</div>
{% endif %}

</body>
</html>
"""

@app.before_request
def setup():
    if not getattr(app, "_db_ready", False):
        try:
            database.init()
            app._db_ready = True
        except Exception as e:
            pass

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
