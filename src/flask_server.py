# flask_server.py
"""
Radhe REST API & Desktop Web Application Server.

Provides:
1. Full REST API for desktop, mobile (Android), and external tools.
2. Responsive Desktop Web Application served directly at GET / with modern UI,
   chat interface, AI provider settings, memory manager, WhatsApp controls,
   and calendar & tasks views.
"""

import os
import logging
import threading
from functools import wraps
from typing import Dict, Any

from flask import Flask, jsonify, request, render_template_string

from command_parser import parser
from command_executor import executor
from ai_providers import ai_provider_manager
from memory import memory_manager
from reminder_manager import default_reminder_manager
from calendar_manager import calendar_manager
from daily_briefing import daily_briefing_manager
from social_media import social_integrator

import llm_setup  # side effect: attaches brain.llm_client

API_TOKEN: str = os.environ.get("RADHE_API_TOKEN", "").strip()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(name)s — %(message)s"
)
logger = logging.getLogger("Radhe_Flask")

app = Flask(__name__)


# ==================================================================
# AUTH DECORATOR
# ==================================================================

def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if API_TOKEN:
            provided = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if provided != API_TOKEN:
                logger.warning("Unauthorized request from %s", request.remote_addr)
                return jsonify({"error": "Unauthorized — invalid or missing token."}), 401
        return f(*args, **kwargs)
    return decorated


# ==================================================================
# DESKTOP WEB INTERFACE (SPA)
# ==================================================================

DESKTOP_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Radhe — Personal AI Companion</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0d1117;
            --sidebar-bg: #161b22;
            --card-bg: #21262d;
            --card-border: #30363d;
            --accent: #58a6ff;
            --accent-glow: rgba(88, 166, 255, 0.25);
            --text: #f0f6fc;
            --text-muted: #8b949e;
            --success: #238636;
            --danger: #da3633;
            --warning: #d29922;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }
        body { background: var(--bg); color: var(--text); display: flex; height: 100vh; overflow: hidden; }
        
        /* Sidebar */
        aside {
            width: 260px; background: var(--sidebar-bg); border-right: 1px solid var(--card-border);
            display: flex; flex-direction: column; justify-content: space-between; padding: 24px 16px;
        }
        .brand { display: flex; align-items: center; gap: 12px; margin-bottom: 32px; padding: 0 8px; }
        .brand-icon {
            width: 40px; height: 40px; background: linear-gradient(135deg, #1f6feb, #58a6ff);
            border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 20px;
            box-shadow: 0 4px 12px var(--accent-glow);
        }
        .brand-text h2 { font-size: 18px; font-weight: 700; letter-spacing: 0.5px; }
        .brand-text p { font-size: 12px; color: var(--text-muted); }

        nav { display: flex; flex-direction: column; gap: 6px; }
        .nav-item {
            display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-radius: 10px;
            color: var(--text-muted); cursor: pointer; font-size: 14px; font-weight: 500;
            transition: all 0.2s ease;
        }
        .nav-item:hover { background: rgba(255, 255, 255, 0.05); color: var(--text); }
        .nav-item.active { background: var(--card-bg); color: var(--accent); border: 1px solid var(--card-border); font-weight: 600; }

        .sidebar-footer { padding: 12px; background: rgba(0, 0, 0, 0.2); border-radius: 10px; font-size: 12px; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #3fb950; display: inline-block; margin-right: 6px; }

        /* Main Content */
        main { flex: 1; display: flex; flex-direction: column; overflow-y: auto; padding: 32px 40px; }
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }
        header h1 { font-size: 24px; font-weight: 700; }

        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.2s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

        /* Cards & Grids */
        .grid-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 20px; margin-bottom: 24px; }
        .card {
            background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 14px;
            padding: 20px; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
        }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .card-title { font-size: 13px; font-weight: 600; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.5px; }
        .card-value { font-size: 20px; font-weight: 700; margin-top: 4px; }

        /* Chat view */
        .chat-container { display: flex; flex-direction: column; height: calc(100vh - 140px); }
        .chat-messages {
            flex: 1; overflow-y: auto; background: var(--card-bg); border: 1px solid var(--card-border);
            border-radius: 14px; padding: 20px; margin-bottom: 16px; display: flex; flex-direction: column; gap: 14px;
        }
        .msg { max-width: 75%; padding: 12px 18px; border-radius: 14px; font-size: 14px; line-height: 1.5; }
        .msg.user { align-self: flex-end; background: #1f6feb; color: #fff; border-bottom-right-radius: 4px; }
        .msg.radhe { align-self: flex-start; background: #30363d; color: var(--text); border-bottom-left-radius: 4px; }

        .chat-input-bar { display: flex; gap: 12px; }
        .chat-input-bar input {
            flex: 1; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px;
            padding: 14px 18px; color: #fff; font-size: 14px; outline: none;
        }
        .chat-input-bar input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
        .btn {
            background: var(--accent); color: #fff; border: none; border-radius: 10px;
            padding: 12px 20px; font-weight: 600; cursor: pointer; transition: all 0.2s; font-size: 14px;
        }
        .btn:hover { opacity: 0.9; transform: translateY(-1px); }
        .btn-success { background: var(--success); }
        .btn-danger { background: var(--danger); }
        .btn-outline { background: transparent; border: 1px solid var(--card-border); color: var(--text); }
        .btn-outline:hover { background: rgba(255, 255, 255, 0.05); }

        /* Tables & Lists */
        table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }
        th, td { text-align: left; padding: 12px 14px; border-bottom: 1px solid var(--card-border); }
        th { color: var(--text-muted); font-size: 12px; text-transform: uppercase; }
        tr:hover { background: rgba(255, 255, 255, 0.02); }
        .badge {
            display: inline-block; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 600;
            text-transform: uppercase; background: rgba(88, 166, 255, 0.15); color: var(--accent);
        }

        /* Forms */
        .form-group { margin-bottom: 16px; }
        .form-group label { display: block; font-size: 13px; color: var(--text-muted); margin-bottom: 6px; font-weight: 500; }
        .form-group select, .form-group input {
            width: 100%; background: var(--bg); border: 1px solid var(--card-border); border-radius: 10px;
            padding: 10px 14px; color: #fff; font-size: 14px; outline: none;
        }
    </style>
</head>
<body>
    <aside>
        <div>
            <div class="brand">
                <div class="brand-icon">✨</div>
                <div class="brand-text">
                    <h2>RADHE</h2>
                    <p>Personal AI Assistant</p>
                </div>
            </div>
            <nav>
                <div class="nav-item active" onclick="switchTab('dashboard')">📊 Dashboard</div>
                <div class="nav-item" onclick="switchTab('chat')">💬 Chat & Voice</div>
                <div class="nav-item" onclick="switchTab('ai')">🤖 AI Settings</div>
                <div class="nav-item" onclick="switchTab('memory')">🧠 Memory</div>
                <div class="nav-item" onclick="switchTab('whatsapp')">📱 WhatsApp</div>
                <div class="nav-item" onclick="switchTab('tasks')">📅 Tasks & Calendar</div>
            </nav>
        </div>
        <div class="sidebar-footer">
            <span class="status-dot"></span> <strong id="active-ai-badge">Groq (LLaMA 3.3)</strong>
            <p style="color: var(--text-muted); margin-top: 4px;">Desktop Connected</p>
        </div>
    </aside>

    <main>
        <!-- DASHBOARD TAB -->
        <section id="tab-dashboard" class="tab-content active">
            <header>
                <div>
                    <h1>Today's Overview</h1>
                    <p style="color: var(--text-muted); margin-top: 4px;" id="current-date-time">Loading date...</p>
                </div>
                <button class="btn btn-outline" onclick="loadDashboard()">🔄 Refresh</button>
            </header>

            <div class="card" style="margin-bottom: 24px;">
                <h3 style="color: var(--accent); font-size: 14px; margin-bottom: 8px;">🌅 MORNING DAILY BRIEFING</h3>
                <p id="briefing-text" style="line-height: 1.6; font-size: 15px;">Loading morning briefing...</p>
            </div>

            <div class="grid-cards">
                <div class="card">
                    <div class="card-title">Active AI Model</div>
                    <div class="card-value" id="card-ai-name">Loading...</div>
                </div>
                <div class="card">
                    <div class="card-title">WhatsApp Mode</div>
                    <div class="card-value" id="card-wa-mode">Monitor</div>
                </div>
                <div class="card">
                    <div class="card-title">Pending Tasks</div>
                    <div class="card-value" id="card-task-count">0 Tasks</div>
                </div>
            </div>
        </section>

        <!-- CHAT TAB -->
        <section id="tab-chat" class="tab-content">
            <header>
                <h1>Interactive Chat with Radhe</h1>
                <span class="badge" id="chat-mode-badge">Bilingual • Ready</span>
            </header>
            <div class="chat-container">
                <div class="chat-messages" id="chat-msgs">
                    <div class="msg radhe">✨ <strong>Radhe:</strong> Namaste! How can I help you today?</div>
                </div>
                <div class="chat-input-bar">
                    <input type="text" id="chat-input" placeholder="Ask Radhe anything, add a task, schedule an event..." onkeypress="if(event.key==='Enter') sendChat()">
                    <button class="btn" onclick="sendChat()">Send</button>
                </div>
            </div>
        </section>

        <!-- AI SETTINGS TAB -->
        <section id="tab-ai" class="tab-content">
            <header>
                <h1>AI Provider Settings (BYOK)</h1>
                <button class="btn btn-success" onclick="saveAISettings()">Save & Apply</button>
            </header>
            <div class="card" style="max-width: 600px;">
                <div class="form-group">
                    <label>Select AI Provider</label>
                    <select id="ai-provider-select" onchange="onProviderChange()">
                        <option value="groq">Groq (Hosted LLaMA)</option>
                        <option value="openai">OpenAI (ChatGPT)</option>
                        <option value="anthropic">Anthropic (Claude)</option>
                        <option value="gemini">Google (Gemini)</option>
                        <option value="ollama">Ollama (Local Models)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Model</label>
                    <select id="ai-model-select"></select>
                </div>
                <div class="form-group">
                    <label>API Key (Bring Your Own Key)</label>
                    <input type="password" id="ai-api-key" placeholder="Enter provider API key">
                </div>
                <div style="display: flex; gap: 10px; margin-top: 16px;">
                    <button class="btn btn-outline" onclick="testAIConnection()">Test Connection</button>
                    <span id="ai-test-result" style="align-self: center; font-size: 13px;"></span>
                </div>
            </div>
        </section>

        <!-- MEMORY TAB -->
        <section id="tab-memory" class="tab-content">
            <header>
                <h1>Personal Memory Management</h1>
                <button class="btn btn-outline" onclick="exportMemory()">💾 Export Data</button>
            </header>
            <div class="card">
                <div style="display: flex; gap: 12px; margin-bottom: 16px;">
                    <input type="text" id="mem-search" placeholder="Search memories..." onkeyup="loadMemories()" style="background: var(--bg); border: 1px solid var(--card-border); border-radius: 8px; padding: 8px 14px; color: #fff; width: 300px;">
                    <button class="btn" onclick="addMemoryPrompt()">➕ Add Memory</button>
                </div>
                <table>
                    <thead>
                        <tr><th>ID</th><th>Category</th><th>Content</th><th>Action</th></tr>
                    </thead>
                    <tbody id="memory-tbody"></tbody>
                </table>
            </div>
        </section>

        <!-- WHATSAPP TAB -->
        <section id="tab-whatsapp" class="tab-content">
            <header>
                <h1>WhatsApp Operations Center</h1>
                <button class="btn btn-outline" onclick="loadWhatsApp()">🔄 Refresh</button>
            </header>
            <div class="card" style="margin-bottom: 20px;">
                <h3 style="font-size: 15px; margin-bottom: 12px;">Operating Mode</h3>
                <div style="display: flex; gap: 16px;">
                    <label><input type="radio" name="wa-mode" value="monitor" onchange="setWAMode('monitor')"> Monitor</label>
                    <label><input type="radio" name="wa-mode" value="approval" onchange="setWAMode('approval')"> Approval</label>
                    <label><input type="radio" name="wa-mode" value="auto_reply" onchange="setWAMode('auto_reply')"> Auto-Reply</label>
                </div>
            </div>
            <div class="card">
                <h3 style="font-size: 15px; margin-bottom: 12px;">Pending Message Approvals</h3>
                <div id="wa-approvals-list"><p style="color: var(--text-muted);">No pending approvals right now.</p></div>
            </div>
        </section>

        <!-- TASKS & CALENDAR TAB -->
        <section id="tab-tasks" class="tab-content">
            <header>
                <h1>Calendar & Task Management</h1>
                <div>
                    <button class="btn btn-outline" onclick="addEventPrompt()">📅 Add Event</button>
                    <button class="btn btn-success" onclick="addTaskPrompt()">➕ Add Task</button>
                </div>
            </header>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div class="card">
                    <h3 style="font-size: 15px; margin-bottom: 12px; color: var(--accent);">To-Do Task List</h3>
                    <div id="task-list-items"></div>
                </div>
                <div class="card">
                    <h3 style="font-size: 15px; margin-bottom: 12px; color: var(--accent);">Calendar Events</h3>
                    <div id="calendar-event-items"></div>
                </div>
            </div>
        </section>
    </main>

    <script>
        function switchTab(name) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            document.getElementById('tab-' + name).classList.add('active');
            event.target.classList.add('active');

            if(name === 'dashboard') loadDashboard();
            if(name === 'ai') loadAISettings();
            if(name === 'memory') loadMemories();
            if(name === 'whatsapp') loadWhatsApp();
            if(name === 'tasks') loadTasksAndCalendar();
        }

        async function loadDashboard() {
            try {
                const res = await fetch('/api/briefing');
                const data = await res.json();
                document.getElementById('briefing-text').innerText = data.spoken_text || 'No briefing available.';
                document.getElementById('current-date-time').innerText = (data.date || '') + ' • ' + (data.time || '');
                document.getElementById('card-wa-mode').innerText = (data.whatsapp_mode || 'monitor').toUpperCase();
                document.getElementById('card-task-count').innerText = (data.pending_tasks?.length || 0) + ' Tasks';
                
                const aiRes = await fetch('/api/ai');
                const aiData = await aiRes.json();
                const actName = (aiData.active_provider || '').toUpperCase();
                document.getElementById('card-ai-name').innerText = actName;
                document.getElementById('active-ai-badge').innerText = actName;
            } catch(e) { console.error(e); }
        }

        async function sendChat() {
            const inp = document.getElementById('chat-input');
            const txt = inp.value.trim();
            if(!txt) return;
            inp.value = '';

            const msgs = document.getElementById('chat-msgs');
            msgs.innerHTML += `<div class="msg user">👤 ${txt}</div>`;
            msgs.scrollTop = msgs.scrollHeight;

            try {
                const res = await fetch('/command', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({command: txt})
                });
                const data = await res.json();
                msgs.innerHTML += `<div class="msg radhe">✨ <strong>Radhe:</strong> ${data.response}</div>`;
                msgs.scrollTop = msgs.scrollHeight;
            } catch(e) {
                msgs.innerHTML += `<div class="msg radhe" style="color: var(--danger)">Error: ${e}</div>`;
            }
        }

        let aiDataCache = null;
        async function loadAISettings() {
            const res = await fetch('/api/ai');
            aiDataCache = await res.json();
            document.getElementById('ai-provider-select').value = aiDataCache.active_provider;
            onProviderChange();
        }

        function onProviderChange() {
            const p = document.getElementById('ai-provider-select').value;
            const provInfo = aiDataCache?.providers?.[p];
            const modSelect = document.getElementById('ai-model-select');
            modSelect.innerHTML = '';
            if(provInfo && provInfo.supported_models) {
                provInfo.supported_models.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m; opt.innerText = m;
                    if(m === provInfo.selected_model) opt.selected = true;
                    modSelect.appendChild(opt);
                });
            }
        }

        async function saveAISettings() {
            const p = document.getElementById('ai-provider-select').value;
            const m = document.getElementById('ai-model-select').value;
            const k = document.getElementById('ai-api-key').value.trim();

            if(k) {
                await fetch('/api/ai/key', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({provider: p, key: k})
                });
            }
            await fetch('/api/ai/select', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({provider: p, model: m})
            });
            alert('AI Settings Saved Successfully!');
            loadDashboard();
        }

        async function testAIConnection() {
            const p = document.getElementById('ai-provider-select').value;
            const el = document.getElementById('ai-test-result');
            el.innerText = 'Testing...';
            const res = await fetch('/api/ai/test', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({provider: p})
            });
            const data = await res.json();
            if(data.status === 'connected') {
                el.innerText = `Connected (${data.latency_ms}ms)`;
                el.style.color = '#3fb950';
            } else {
                el.innerText = 'Failed: ' + (data.message || 'Error');
                el.style.color = '#da3633';
            }
        }

        async function loadMemories() {
            const q = document.getElementById('mem-search')?.value || '';
            const res = await fetch('/api/memory?query=' + encodeURIComponent(q));
            const list = await res.json();
            const tb = document.getElementById('memory-tbody');
            tb.innerHTML = '';
            list.forEach(m => {
                tb.innerHTML += `<tr>
                    <td>${m.id}</td>
                    <td><span class="badge">${m.type}</span></td>
                    <td>${m.text}</td>
                    <td><button class="btn btn-outline" style="padding: 4px 8px; font-size: 11px;" onclick="deleteMemory(${m.id})">Delete</button></td>
                </tr>`;
            });
        }

        async function deleteMemory(id) {
            if(!confirm('Delete this memory?')) return;
            await fetch('/api/memory/' + id, {method: 'DELETE'});
            loadMemories();
        }

        async function addMemoryPrompt() {
            const text = prompt('Enter fact to remember:');
            if(!text) return;
            await fetch('/api/memory', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: text})
            });
            loadMemories();
        }

        async function exportMemory() {
            const res = await fetch('/api/memory/export');
            const data = await res.json();
            alert('Export generated: ' + data.path);
        }

        async function loadWhatsApp() {
            const res = await fetch('/api/whatsapp');
            const data = await res.json();
            const radios = document.getElementsByName('wa-mode');
            radios.forEach(r => { if(r.value === data.mode) r.checked = true; });
        }

        async function setWAMode(m) {
            await fetch('/api/whatsapp/mode', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mode: m})
            });
            alert('WhatsApp mode set to ' + m);
        }

        async function loadTasksAndCalendar() {
            // Load tasks
            const tRes = await fetch('/api/tasks');
            const tasks = await tRes.json();
            const tDiv = document.getElementById('task-list-items');
            tDiv.innerHTML = '';
            if(tasks.length === 0) tDiv.innerHTML = '<p style="color:var(--text-muted)">No pending tasks.</p>';
            tasks.forEach(t => {
                tDiv.innerHTML += `<div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid var(--card-border)">
                    <span>• ${t.title} <span class="badge">${t.priority}</span></span>
                    <button class="btn btn-outline" style="padding:2px 6px; font-size:11px" onclick="completeTask(${t.id})">Done</button>
                </div>`;
            });

            // Load calendar
            const cRes = await fetch('/api/calendar');
            const events = await cRes.json();
            const cDiv = document.getElementById('calendar-event-items');
            cDiv.innerHTML = '';
            if(events.length === 0) cDiv.innerHTML = '<p style="color:var(--text-muted)">No scheduled events.</p>';
            events.forEach(e => {
                cDiv.innerHTML += `<div style="padding:8px 0; border-bottom:1px solid var(--card-border)">
                    <strong>${e.title}</strong><br><small style="color:var(--text-muted)">${e.start_time.substring(0, 16).replace('T', ' ')}</small>
                </div>`;
            });
        }

        async function completeTask(id) {
            await fetch(`/api/tasks/${id}/complete`, {method: 'POST'});
            loadTasksAndCalendar();
        }

        async function addTaskPrompt() {
            const title = prompt('Enter new task:');
            if(!title) return;
            await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: title})
            });
            loadTasksAndCalendar();
        }

        async function addEventPrompt() {
            const title = prompt('Event Title:');
            if(!title) return;
            const time = prompt('Time (e.g. tomorrow at 4pm):');
            if(!time) return;
            const res = await fetch('/api/calendar', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: title, time: time})
            });
            const data = await res.json();
            if(data.conflicts && data.conflicts.length > 0) {
                alert('Event added, but CONFLICT detected with: ' + data.conflicts[0].title);
            } else {
                alert('Event scheduled successfully!');
            }
            loadTasksAndCalendar();
        }

        // Auto load dashboard on startup
        window.onload = loadDashboard;
    </script>
</body>
</html>
"""


# ==================================================================
# WEB APP ROUTE
# ==================================================================

@app.get("/")
def desktop_app():
    """Serves the Desktop Single Page Application."""
    return render_template_string(DESKTOP_HTML)


# ==================================================================
# REST API ENDPOINTS
# ==================================================================

@app.get("/status")
def status():
    """Health check endpoint."""
    return jsonify({
        "status": "running",
        "message": "Radhe is online.",
        "active_ai": ai_provider_manager.get_active_provider_name(),
        "whatsapp_mode": social_integrator.get_mode(),
    }), 200


@app.post("/command")
@require_token
def command():
    """Execute text command via Radhe NLP pipeline."""
    data = request.get_json(silent=True) or {}
    text = (data.get("command") or "").strip()
    if not text:
        return jsonify({"error": "'command' field is required."}), 400

    try:
        parsed = parser.parse(text)
        result = executor.execute(parsed, text)
        response_text = result.get("text") or result.get("response") or ""
        return jsonify({"response": response_text, "success": True}), 200
    except Exception as e:
        logger.exception("Command error: %s", e)
        return jsonify({"error": str(e)}), 500


# ── AI Providers API ──────────────────────────────────────────────────

@app.get("/api/ai")
def get_ai_status():
    return jsonify(ai_provider_manager.get_all_provider_status()), 200


@app.post("/api/ai/select")
def select_ai_provider():
    data = request.get_json(silent=True) or {}
    p = data.get("provider")
    m = data.get("model")
    if not p:
        return jsonify({"error": "provider is required"}), 400
    ok, msg = ai_provider_manager.set_active_provider(p, m)
    return jsonify({"success": ok, "message": msg}), (200 if ok else 400)


@app.post("/api/ai/key")
def set_ai_key():
    data = request.get_json(silent=True) or {}
    p = data.get("provider")
    k = data.get("key", "")
    if not p:
        return jsonify({"error": "provider is required"}), 400
    ok, msg = ai_provider_manager.set_api_key(p, k)
    return jsonify({"success": ok, "message": msg}), 200


@app.post("/api/ai/test")
def test_ai():
    data = request.get_json(silent=True) or {}
    p = data.get("provider") or ai_provider_manager.get_active_provider_name()
    res = ai_provider_manager.test_provider(p)
    return jsonify(res), 200


# ── Memory API ────────────────────────────────────────────────────────

@app.get("/api/memory")
def get_memories():
    q = request.args.get("query", "")
    cat = request.args.get("category")
    results = memory_manager.search_memories(query=q, category=cat, limit=100)
    return jsonify(results), 200


@app.post("/api/memory")
def add_memory():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    cat = data.get("category", "general")
    if not text:
        return jsonify({"error": "text is required"}), 400
    res = memory_manager.add_memory(text=text, category=cat)
    return jsonify(res), 201


@app.delete("/api/memory/<int:mem_id>")
def delete_memory(mem_id: int):
    ok = memory_manager.delete_memory_by_id(mem_id)
    return jsonify({"success": ok}), (200 if ok else 404)


@app.get("/api/memory/export")
def export_memories():
    fmt = request.args.get("format", "json")
    path = memory_manager.export_data(format=fmt)
    return jsonify({"success": True, "path": path}), 200


# ── WhatsApp API ──────────────────────────────────────────────────────

@app.get("/api/whatsapp")
def get_whatsapp():
    return jsonify({
        "mode": social_integrator.get_mode(),
        "pending_approvals": social_integrator.get_pending_approvals() if hasattr(social_integrator, "get_pending_approvals") else []
    }), 200


@app.post("/api/whatsapp/mode")
def set_whatsapp_mode():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "monitor")
    msg = social_integrator.set_mode(mode)
    return jsonify({"success": True, "message": msg, "mode": social_integrator.get_mode()}), 200


# ── Tasks API ─────────────────────────────────────────────────────────

@app.get("/api/tasks")
def get_tasks():
    status = request.args.get("status", "pending")
    tasks = default_reminder_manager.list_tasks(status=status)
    return jsonify(tasks), 200


@app.post("/api/tasks")
def add_task():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "")
    prio = data.get("priority", "medium")
    if not title:
        return jsonify({"error": "title is required"}), 400
    tid = default_reminder_manager.add_task(title=title, priority=prio)
    return jsonify({"success": True, "id": tid}), 201


@app.post("/api/tasks/<int:task_id>/complete")
def complete_task(task_id: int):
    ok = default_reminder_manager.complete_task(task_id)
    return jsonify({"success": ok}), 200


@app.delete("/api/tasks/<int:task_id>")
def delete_task(task_id: int):
    ok = default_reminder_manager.delete_task(task_id)
    return jsonify({"success": ok}), 200


# ── Calendar API ──────────────────────────────────────────────────────

@app.get("/api/calendar")
def get_calendar():
    events = calendar_manager.get_events(limit=50)
    return jsonify(events), 200


@app.post("/api/calendar")
def create_calendar_event():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "")
    time_str = data.get("time", "")
    if not title or not time_str:
        return jsonify({"error": "title and time are required"}), 400
    res = calendar_manager.create_event(title, time_str)
    return jsonify(res), 201


# ── Daily Briefing API ────────────────────────────────────────────────

@app.get("/api/briefing")
def get_daily_briefing():
    lang = request.args.get("language", "en")
    briefing = daily_briefing_manager.generate_briefing(language=lang)
    return jsonify(briefing), 200


# ==================================================================
# SERVER LAUNCHER
# ==================================================================

def start_flask_server(host: str = "0.0.0.0", port: int = 5000, debug: bool = False) -> threading.Thread:
    """Run Flask server in background thread."""
    def _run():
        logger.info("Radhe Desktop Web App & API running at http://localhost:%d", port)
        app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=False)

    t = threading.Thread(target=_run, name="RadheFlaskServer", daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    logger.info("Starting Radhe Desktop App & REST Server...")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
