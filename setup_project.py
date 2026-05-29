import os

# Define the file contents
app_code = """from flask import Flask, render_template, request, redirect, session, jsonify
import requests
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup

app = Flask(__name__)
app.secret_key = "telecom_secure_session_key_2026"

# Base Configurations from uploaded files
BASE = "http://51.210.208.26/ints"
LOGIN_URL = BASE + "/login"
SIGNIN_URL = BASE + "/signin"
ACTION_BASE = BASE.replace("/ints/", "/nints/")

# Endpoints
RANGES_URL = BASE + "/client/res/aj_smsranges.php"
NUMBERS_URL = BASE + "/client/res/data_smsnumbers.php"
DASHBOARD_URL = BASE + "/client/SMSDashboard"
CLIENT_CDR_URL = BASE + "/client/res/data_smscdr.php"
CLIENT_CDR_PAGE = BASE + "/client/SMSCDRStats"

AGENT_BULK_URL = BASE + "/agent/SMSBulkAllocations"
AGENT_DATA_RANGES = BASE + "/agent/res/data_smsranges.php"
AGENT_REQUEST_URL = ACTION_BASE + "/agent/res/requestsmsnumberfinal.php"

AGENT_USERNAME = "Ashok20"
AGENT_PASSWORD = "aura20"

# ---------------- HELPER UTILITIES ----------------

def clean_html(text):
    if not text:
        return ""
    return BeautifulSoup(str(text), "html.parser").get_text().strip()

def solve_captcha(session_obj, url):
    try:
        response = session_obj.get(url)
        match = re.search(r"What is\\s+(\\d+)\\s*\\+\\s*(\\d+)", response.text)
        if match:
            return int(match.group(1)) + int(match.group(2))
    except Exception as e:
        print(f"[-] Captcha parse error: {e}")
    return None

def extract_real_numeric_id(row_data):
    patterns = [
        r'info=["\\'](\\d+)["\\']',
        r'rid=["\\'](\\d+)["\\']',
        r'id=["\\']\\w*?_?(\\d+)["\\']',
        r'value=["\\'](\\d+)["\\']',
        r'href=.*?[=\\(/](\\d+)[\\)/"\\']'
    ]
    for cell in row_data:
        cell_str = str(cell)
        for pattern in patterns:
            match = re.search(pattern, cell_str, re.IGNORECASE)
            if match:
                return match.group(1)
    for cell in row_data:
        cleaned = clean_html(cell)
        if cleaned.isdigit() and 2 <= len(cleaned) <= 5:
            return cleaned
    return None

def restore_client_session():
    cookies = session.get("remote_cookies")
    if not cookies:
        return None
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    })
    s.cookies.update(cookies)
    return s

def get_agent_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    })
    captcha = solve_captcha(s, LOGIN_URL)
    if captcha is None:
        return None
    payload = {"username": AGENT_USERNAME, "password": AGENT_PASSWORD, "capt": str(captcha)}
    resp = s.post(SIGNIN_URL, data=payload, headers={"Origin": "http://51.210.208.26", "Referer": LOGIN_URL}, allow_redirects=True)
    if "/agent/" not in resp.url:
        return None
    return s

# ---------------- CORE ROUTES ----------------

@app.route("/")
def home():
    if session.get("logged_in") and restore_client_session():
        return redirect("/dashboard")
    session.clear()
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"})
    captcha = solve_captcha(s, LOGIN_URL)
    
    if captcha is None:
        return render_template("login.html", error="Verification math puzzle parsing error.")
        
    payload = {"username": username, "password": password, "capt": str(captcha)}
    resp = s.post(SIGNIN_URL, data=payload, headers={"Origin": "http://51.210.208.26", "Referer": LOGIN_URL}, allow_redirects=True)
    
    if "/client/" not in resp.url:
        return render_template("login.html", error="Client credentials rejected.")
        
    session["logged_in"] = True
    session["username"] = username
    session["remote_cookies"] = requests.utils.dict_from_cookiejar(s.cookies)
    return redirect("/dashboard")

@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"): return redirect("/")
    client_session = restore_client_session()
    
    stats = {"today": "0", "last7": "0", "last30": "0"}
    if client_session:
        try:
            r = client_session.get(DASHBOARD_URL)
            today = re.search(r"Today SMS.*?(\\d+)", r.text, re.S)
            last7 = re.search(r"Last 7 Day SMS.*?(\\d+)", r.text, re.S)
            last30 = re.search(r"Last 30 Day SMS.*?(\\d+)", r.text, re.S)
            stats = {
                "today": today.group(1) if today else "0",
                "last7": last7.group(1) if last7 else "0",
                "last30": last30.group(1) if last30 else "0"
            }
        except:
            pass
            
    return render_template("dashboard_home.html", username=session.get("username"), stats=stats)

@app.route("/my-numbers")
def my_numbers():
    if not session.get("logged_in"): return redirect("/")
    return render_template("dashboard.html", username=session.get("username"))

@app.route("/api/numbers")
def api_numbers():
    client_session = restore_client_session()
    if not client_session: return jsonify({"error": "Unauthorized"}), 401
    
    all_rows = []
    try:
        r = client_session.get(RANGES_URL, params={"max": 100, "page": 1}, headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})
        ranges = r.json().get("results", [])
        range_ids = [rng["id"] for rng in ranges if "id" in rng]
        
        for rid in range_ids:
            params = {"frange": rid, "fclient": "", "sEcho": "1", "iColumns": "6", "iDisplayStart": "0", "iDisplayLength": "100", "_": str(int(time.time() * 1000))}
            num_resp = client_session.get(NUMBERS_URL, params=params, headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})
            all_rows.extend(num_resp.json().get("aaData", []))
    except Exception as e:
        print(f"Fetch numbers error: {e}")
        
    return jsonify({"aaData": all_rows})

@app.route("/allocate")
def allocate_page():
    if not session.get("logged_in"): return redirect("/")
    agent_session = get_agent_session()
    processed_list = []
    
    if agent_session:
        agent_session.get(BASE + "/agent/SMSRanges")
        params = {'sEcho': '1', 'iColumns': '10', 'iDisplayStart': '0', 'iDisplayLength': '-1'}
        r = agent_session.get(AGENT_DATA_RANGES, params=params, headers={"X-Requested-With": "XMLHttpRequest"})
        raw_table_rows = r.json().get("aaData", [])
        
        for index, row in enumerate(raw_table_rows):
            real_numeric_id = extract_real_numeric_id(row)
            name_string = clean_html(row[0])
            route_string = clean_html(row[1]) if len(row) > 1 else ""
            stock_value = clean_html(row[4]) if len(row) > 4 else "NA"
            display_label = name_string if name_string else route_string
            if not real_numeric_id: real_numeric_id = f"NOT_FOUND_{index}"
            
            processed_list.append({
                "db_id": real_numeric_id,
                "label": display_label,
                "stock": stock_value
            })
            
    return render_template("allocate.html", username=session.get("username"), ranges=processed_list)

@app.route("/api/allocate", methods=["POST"])
def api_allocate():
    if not session.get("logged_in"): return jsonify({"success": False, "message": "Unauthorized"}), 401
    
    chosen_rid = request.json.get("rid")
    qty_requested = request.json.get("qty")
    username = session.get("username")
    
    agent_session = get_agent_session()
    if not agent_session: return jsonify({"success": False, "message": "System Agent session failed"})
    
    # Resolve client_id mapping
    client_id = None
    try:
        r = agent_session.get(AGENT_BULK_URL)
        soup = BeautifulSoup(r.text, "html.parser")
        for opt in soup.select("#xclient option[value]"):
            if opt.get_text(strip=True).lower() == username.lower():
                client_id = opt["value"]
                break
    except:
        pass
        
    if not client_id: return jsonify({"success": False, "message": "Database mapping lookup error"})
    
    # Pass 1 Allocation
    payload = {"action": "allocate", "ntype": "-2", "range[]": str(chosen_rid), "client[]": str(client_id), "payterm": "1", "payout": "0", "qty": str(qty_requested)}
    r = agent_session.post(AGENT_BULK_URL, data=payload, headers={"Referer": AGENT_BULK_URL}, allow_redirects=True)
    
    if "allocated" in r.text.lower():
        return jsonify({"success": True, "message": "Direct Allocation Successful!"})
        
    # Pass 2 Fallback Matrix Request
    request_payload = {"rid": str(chosen_rid), "payterm": "2", "qty": str(qty_requested)}
    request_headers = {"Origin": "http://51.210.208.26", "Referer": ACTION_BASE + "agent/SMSRanges", "X-Requested-With": "XMLHttpRequest"}
    agent_session.post(AGENT_REQUEST_URL, data=request_payload, headers=request_headers)
    
    # Pass 3 Final Verification Pass
    retry = agent_session.post(AGENT_BULK_URL, data=payload, headers={"Referer": AGENT_BULK_URL}, allow_redirects=True)
    if "allocated" in retry.text.lower():
        return jsonify({"success": True, "message": "Allocation successfully claimed via secondary routing line!"})
        
    return jsonify({"success": False, "message": "All pipeline allocation instances returned standard execution failures"})

@app.route("/report", methods=["GET", "POST"])
def report():
    if not session.get("logged_in"): return redirect("/")
    client_session = restore_client_session()
    
    records = []
    target_date = request.form.get("date", datetime.today().strftime('%Y-%m-%d'))
    
    if request.method == "POST" and client_session:
        client_session.get(CLIENT_CDR_PAGE)
        params = {
            "fdate1": f"{target_date} 00:00:00", "fdate2": f"{target_date} 23:59:59",
            "frange": "", "fnum": "", "fcli": "", "fgdate": "", "fgmonth": "",
            "fgrange": "", "fgnumber": "", "fgcli": "", "fg": "0", "sEcho": "2",
            "iColumns": "7", "sColumns": ",,,,,,,", "iDisplayStart": "0", "iDisplayLength": "-1",
            "sSearch": "", "bRegex": "false", "iSortCol_0": "0", "sSortDir_0": "desc", "iSortingCols": "1",
            "_": str(int(time.time() * 1000))
        }
        for i in range(7): 
            params[f"mDataProp_{i}"] = str(i)
            params[f"bRegex_{i}"] = "false"
            params[f"bSearchable_{i}"] = "true"
            params[f"bSortable_{i}"] = "true"
            
        try:
            res = client_session.get(CLIENT_CDR_URL, params=params, headers={"X-Requested-With": "XMLHttpRequest", "Referer": CLIENT_CDR_PAGE})
            raw_records = res.json().get("aaData", [])
            for row in raw_records:
                records.append([clean_html(cell) for cell in row])
        except Exception as e:
            print(f"CDR processing fault: {e}")
            
    return render_template("report.html", username=session.get("username"), records=records, target_date=target_date)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
"""

base_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Telecom Provisioning Matrix</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    <style>
        body { background-color: #f8f9fa; }
        .sidebar { min-height: 100vh; background-color: #212529; color: white; padding-top: 20px; }
        .sidebar a { color: #adbcda; text-decoration: none; display: block; padding: 12px 20px; }
        .sidebar a:hover, .sidebar a.active { background-color: #343a40; color: white; }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="row">
            {% if session.get('logged_in') %}
            <div class="col-md-2 sidebar px-0">
                <h5 class="text-center text-white mb-4">Telecom Portal</h5>
                <p class="text-muted text-center small">User: {{ username }}</p>
                <hr class="bg-secondary">
                <a href="/dashboard">📊 Dashboard</a>
                <a href="/my-numbers">🔢 My Numbers</a>
                <a href="/allocate">⚡ Allocation Setup</a>
                <a href="/report">📑 CDR Reports</a>
                <hr class="bg-secondary">
                <a href="/logout" class="text-danger">🚪 Log Out</a>
            </div>
            <div class="col-md-10 p-4">
                {% block content %}{% endblock %}
            </div>
            {% else %}
            <div class="col-12 p-0">
                {% block login_content %}{% endblock %}
            </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

login_html = """{% extends "base.html" %}
{% block login_content %}
<div class="container d-flex justify-content-center align-items-center" style="min-height: 100vh;">
    <div class="card p-4 shadow" style="width: 400px;">
        <h3 class="text-center mb-4">Portal Gateway Login</h3>
        {% if error %}
            <div class="alert alert-danger">{{ error }}</div>
        {% endif %}
        <form action="/login" method="POST">
            <div class="mb-3">
                <label class="form-label">Client Username</label>
                <input type="text" name="username" class="form-control" placeholder="e.g. Ashok20" required>
            </div>
            <div class="mb-3">
                <label class="form-label">Password</label>
                <input type="password" name="password" class="form-control" placeholder="e.g. aura20" required>
            </div>
            <button type="submit" class="btn btn-primary w-100">Authenticate Pipeline</button>
        </form>
    </div>
</div>
{% endblock %}
"""

dashboard_home_html = """{% extends "base.html" %}
{% block content %}
<h2 class="mb-4">System Operational Dashboard Overview</h2>
<div class="row g-4">
    <div class="col-md-4">
        <div class="card bg-primary text-white p-4 shadow-sm">
            <h5>Today's SMS Volume</h5>
            <h2 class="display-5 font-weight-bold">{{ stats.today }}</h2>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card bg-success text-white p-4 shadow-sm">
            <h5>Last 7 Days Run Total</h5>
            <h2 class="display-5 font-weight-bold">{{ stats.last7 }}</h2>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card bg-dark text-white p-4 shadow-sm">
            <h5>Last 30 Days Running Metrics</h5>
            <h2 class="display-5 font-weight-bold">{{ stats.last30 }}</h2>
        </div>
    </div>
</div>
{% endblock %}
"""

dashboard_html = """{% extends "base.html" %}
{% block content %}
<h2 class="mb-4">Allocated Numbers Real-time Index</h2>
<div class="card shadow-sm p-4">
    <div class="table-responsive">
        <table class="table table-striped" id="numbersTable">
            <thead>
                <tr>
                    <th>Line Index ID</th>
                    <th>Assigned Object Line Number</th>
                    <th>Current System Destination Route Context</th>
                    <th>State/Status Flag</th>
                </tr>
            </thead>
            <tbody id="numbersBody">
                <tr><td colspan="4" class="text-center text-muted">Polling current target allocation stream array...</td></tr>
            </tbody>
        </table>
    </div>
</div>

<script>
    document.addEventListener("DOMContentLoaded", function() {
        fetch('/api/numbers')
            .then(res => res.json())
            .then(data => {
                const tbody = document.getElementById("numbersBody");
                tbody.innerHTML = "";
                if(!data.aaData || data.aaData.length === 0) {
                    tbody.innerHTML = "<tr><td colspan='4' class='text-center'>No active inventory lines mapped.</td></tr>";
                    return;
                }
                data.aaData.forEach((row, idx) => {
                    let tr = document.createElement("tr");
                    tr.innerHTML = `<td>${idx + 1}</td>
                                    <td><strong>${row[0] || 'N/A'}</strong></td>
                                    <td>${row[1] || 'N/A'}</td>
                                    <td><span class="badge bg-success">${row[2] || 'Active'}</span></td>`;
                    tbody.appendChild(tr);
                });
            });
    });
</script>
{% endblock %}
"""

allocate_html = """{% extends "base.html" %}
{% block content %}
<h2 class="mb-4">System Routing Allocation Engine</h2>
<div class="row">
    <div class="col-md-7">
        <div class="card shadow-sm p-4">
            <h5 class="mb-3">Request Target Routing Allocation</h5>
            <div class="mb-3">
                <label class="form-label">Target System Range Channel</label>
                <select id="rangeSelect" class="form-select">
                    {% for rng in ranges %}
                        <option value="{{ rng.db_id }}">ID: {{ rng.db_id }} | {{ rng.label }} (Stock: {{ rng.stock }})</option>
                    {% endfor %}
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">Allocation Limit Quantity</label>
                <input type="number" id="qtyInput" class="form-control" value="10" min="1">
            </div>
            <button onclick="triggerAllocation()" class="btn btn-warning w-100">Process Twin-Pass Matrix Push</button>
            <div id="statusMessage" class="mt-3"></div>
        </div>
    </div>
</div>

<script>
    function triggerAllocation() {
        const rid = document.getElementById("rangeSelect").value;
        const qty = document.getElementById("qtyInput").value;
        const statusDiv = document.getElementById("statusMessage");
        
        statusDiv.innerHTML = `<div class="alert alert-info">Executing script allocation channels... Please hold.</div>`;
        
        fetch('/api/allocate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rid: rid, qty: qty })
        })
        .then(res => res.json())
        .then(data => {
            if(data.success) {
                statusDiv.innerHTML = `<div class="alert alert-success">${data.message}</div>`;
            } else {
                statusDiv.innerHTML = `<div class="alert alert-danger">${data.message}</div>`;
            }
        });
    }
</script>
{% endblock %}
"""

report_html = """{% extends "base.html" %}
{% block content %}
<h2 class="mb-4">Unlimited Data Stream CDR Reporting Summary</h2>
<div class="card shadow-sm p-4 mb-4">
    <form method="POST" class="row g-3 align-items-end">
        <div class="col-auto">
            <label class="form-label">Query Window Date Target</label>
            <input type="date" name="date" class="form-control" value="{{ target_date }}">
        </div>
        <div class="col-auto">
            <button type="submit" class="btn btn-dark">Pull Complete Stream Dataset</button>
        </div>
    </form>
</div>

<div class="card shadow-sm p-4">
    <div class="table-responsive">
        <table class="table table-bordered table-hover">
            <thead class="table-light">
                <tr>
                    <th>#</th>
                    <th>Timestamp Data Line</th>
                    <th>Origin Context</th>
                    <th>Target Context</th>
                    <th>Message Parameters</th>
                    <th>Status System Flag</th>
                    <th>Cost Vector Allocation</th>
                </tr>
            </thead>
            <tbody>
                {% if records %}
                    {% for row in records %}
                    <tr>
                        <td>{{ loop.index }}</td>
                        {% for cell in row[:6] %}
                            <td>{{ cell }}</td>
                        {% endfor %}
                    </tr>
                    {% endfor %}
                {% else %}
                    <tr><td colspan="7" class="text-center text-muted">No records retrieved for the configured parameters target query.</td></tr>
                {% endif %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
"""

requirements_txt = """
Flask==3.0.2
requests==2.31.0
beautifulsoup4==4.12.3
gunicorn==21.2.0
"""

procfile_content = """
web: gunicorn app:app
"""

# Map paths to content
files_to_create = {
    "telecom_portal/app.py": app_code,
    "telecom_portal/requirements.txt": requirements_txt,
    "telecom_portal/Procfile": procfile_content,
    "telecom_portal/templates/base.html": base_html,
    "telecom_portal/templates/login.html": login_html,
    "telecom_portal/templates/dashboard_home.html": dashboard_home_html,
    "telecom_portal/templates/dashboard.html": dashboard_html,
    "telecom_portal/templates/allocate.html": allocate_html,
    "telecom_portal/templates/report.html": report_html
}

# Execution flow
if __name__ == "__main__":
    print("[*] Starting structure creation engine...")
    
    # Generate directories
    os.makedirs("telecom_portal/templates", exist_ok=True)
    
    # Write components
    for path, content in files_to_create.items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")
        print(f"[+] Created file: {path}")
        
    print("\\n[SUCCESS] Project structure complete! Ready for local use or direct Railway deployment.")
