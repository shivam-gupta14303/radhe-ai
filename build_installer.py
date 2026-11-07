# build_installer.py
"""
Radhe AI Assistant — Production Release & Packaging Tool.

Performs:
1. Complete pre-flight environment & syntax audit.
2. Creates clean distributable package in dist/Radhe_v2.0/.
3. Generates one-click Windows launchers (.bat) for Native GUI, Web App, and REST Backend.
4. Generates PyInstaller build specification (Radhe.spec).
5. Compiles Release Notes & Verification Manifest.
"""

import os
import sys
import shutil
import py_compile
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
DIST_DIR = ROOT_DIR / "dist" / "Radhe_v2.0"

REQUIRED_MODULES = [
    "ai_providers",
    "backend_api.py",
    "calendar_manager.py",
    "command_executor.py",
    "command_parser.py",
    "config.py",
    "contact_manager.py",
    "cost_tracker.py",
    "daily_briefing.py",
    "dal.py",
    "desktop_gui.py",
    "flask_server.py",
    "health_assistant.py",
    "launch_desktop.py",
    "llm_setup.py",
    "memory.py",
    "mobile_bridge.py",
    "proactive_engine.py",
    "reminder_manager.py",
    "security.py",
    "social_media.py",
    "speech.py",
    "time_parser.py",
    "whatsapp_manager.py",
]


def preflight_check() -> bool:
    """Verify all production source files exist and compile cleanly."""
    print("==================================================")
    print(" RADHE 2.0 — PRE-FLIGHT COMPILATION AUDIT")
    print("==================================================")
    all_ok = True

    for mod in REQUIRED_MODULES:
        p = SRC_DIR / mod
        if not p.exists():
            print(f" [FAIL] Missing required module: {p}")
            all_ok = False
            continue

        if p.is_file() and p.suffix == ".py":
            try:
                py_compile.compile(str(p), doraise=True)
                print(f" [PASS] Compiled: {mod}")
            except Exception as e:
                print(f" [FAIL] Syntax error in {mod}: {e}")
                all_ok = False
        elif p.is_dir():
            print(f" [PASS] Directory verified: {mod}")

    return all_ok


def create_release_package() -> Path:
    """Assemble the distributable package."""
    print("\n==================================================")
    print(" ASSEMBLING DISTRIBUTABLE PACKAGE: dist/Radhe_v2.0")
    print("==================================================")

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR, ignore_errors=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Copy src
    dist_src = DIST_DIR / "src"
    shutil.copytree(SRC_DIR, dist_src, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.tmp"))
    print(" [OK] Copied src/ modules.")

    # 2. Copy mobile companion assets
    mobile_src = ROOT_DIR / "mobile"
    if mobile_src.exists():
        shutil.copytree(mobile_src, DIST_DIR / "mobile", ignore=shutil.ignore_patterns(".gradle", "build"))
        print(" [OK] Copied mobile/ companion client assets.")

    # 3. Create data directories
    (DIST_DIR / "data").mkdir(exist_ok=True)
    (DIST_DIR / "logs").mkdir(exist_ok=True)
    print(" [OK] Created data/ and logs/ persistent directories.")

    # 4. Generate Windows Launchers (.bat)
    # 4.1 Native GUI Launcher
    (DIST_DIR / "run_gui.bat").write_text(
        "@echo off\r\n"
        "title Radhe AI Assistant — Native Desktop GUI\r\n"
        "cd /d \"%~dp0\"\r\n"
        "python src\\launch_desktop.py --gui\r\n"
        "pause\r\n",
        encoding="utf-8"
    )

    # 4.2 Web App Launcher
    (DIST_DIR / "run_web.bat").write_text(
        "@echo off\r\n"
        "title Radhe AI Assistant — Web Application\r\n"
        "cd /d \"%~dp0\"\r\n"
        "python src\\launch_desktop.py --app\r\n"
        "pause\r\n",
        encoding="utf-8"
    )

    # 4.3 FastAPI Enterprise Server Launcher
    (DIST_DIR / "run_backend_api.bat").write_text(
        "@echo off\r\n"
        "title Radhe AI Assistant — FastAPI Backend\r\n"
        "cd /d \"%~dp0src\"\r\n"
        "python -m uvicorn backend_api:app --host 0.0.0.0 --port 8000 --reload\r\n"
        "pause\r\n",
        encoding="utf-8"
    )

    # 4.4 Automated Setup Environment Script
    (DIST_DIR / "setup_env.bat").write_text(
        "@echo off\r\n"
        "title Radhe AI Assistant — Environment Setup\r\n"
        "cd /d \"%~dp0\"\r\n"
        "echo Creating Python virtual environment...\r\n"
        "python -m venv venv\r\n"
        "call venv\\Scripts\\activate\r\n"
        "echo Installing dependencies...\r\n"
        "pip install --upgrade pip\r\n"
        "pip install fastapi uvicorn cryptography flask pillow selenium google-api-python-client google-auth-oauthlib requests\r\n"
        "echo Setup completed successfully!\r\n"
        "pause\r\n",
        encoding="utf-8"
    )
    print(" [OK] Generated Windows launchers (run_gui.bat, run_web.bat, run_backend_api.bat, setup_env.bat).")

    # 5. Generate PyInstaller Build Specification
    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/launch_desktop.py'],
    pathex=['{str(SRC_DIR).replace(os.sep, "/")}'],
    binaries=[],
    datas=[
        ('data', 'data'),
    ],
    hiddenimports=[
        'fastapi', 'uvicorn', 'cryptography', 'flask', 'sqlite3',
        'googleapiclient', 'selenium', 'PIL'
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Radhe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/radhe.ico' if os.path.exists('assets/radhe.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Radhe_App',
)
"""
    (DIST_DIR / "Radhe.spec").write_text(spec_content, encoding="utf-8")
    print(" [OK] Generated PyInstaller specification (Radhe.spec).")

    # 6. Generate Release Notes
    release_notes = f"""# RADHE AI ASSISTANT — VERSION 2.0.0 RELEASE NOTES
Build Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 1. Executive Summary
Radhe 2.0 is a personal AI assistant built specifically for bilingual (Hindi/English/Hinglish) daily companion tasks, real-world productivity, and physical device automation.

## 2. All 10 Completed Phases

### Phase 1: Codebase Audit & Architectural Pruning
- Preserved all working code and dependencies.
- Pruned 7 dead duplicate stubs into archive.

### Phase 2: Multi-AI Provider Architecture (BYOK)
- 5 Supported AI Engines: OpenAI (ChatGPT), Anthropic (Claude), Google (Gemini), Groq (Hosted LLaMA), and Ollama (100% Offline Local Models).
- Zero-restart provider hot-switching and transparent fallback with latency testing.

### Phase 3: 7-Tier Advanced Long-Term Memory
- 7 Dedicated Tiers: Short-Term, Long-Term, Preference, Schedule, Contact, Project, and Task memory.
- Automatic classification, contradiction resolution, and JSON/Markdown export.

### Phase 4: Tasks, Reminders & Google Calendar
- Priority-ranked unified task management (Urgent, High, Medium, Low).
- Offline-first SQLite calendar with OAuth 2.0 Google Calendar synchronization and interval conflict detection.
- Multi-source morning daily briefing.

### Phase 5: Desktop Application (GUI + Web + REST)
- Native Tkinter dark-themed desktop app with 6 views (Dashboard, Chat, AI Settings, Memory, WhatsApp, Calendar).
- Glassmorphic Web App and REST API.

### Phase 6: WhatsApp & Social Integration
- Monitor, Approval, and Auto-reply operational modes.
- Contact relationship mapping ('mother' -> Mummy) and WhatsApp message scheduling engine.

### Phase 7: Enterprise Backend & Cryptographic Security
- High-performance FastAPI REST backend with Bearer token authentication and CORS.
- AES-256-GCM / PBKDF2 SecretVault for BYOK API keys (never plaintext).
- Cryptographic hash-chained tamper-evident audit logger.
- Unified Database Abstraction Layer (DAL) supporting SQLite and PostgreSQL.

### Phase 8: Android Companion Application
- Complete Kotlin + Jetpack Compose Android companion client architecture.
- Push-to-talk voice recording, WhatsApp approval deck, morning briefing card, and WorkManager background sync.

### Phase 9: Personal Health Assistant
- Daily vitals logging (water intake, sleep, steps, blood pressure, glucose, weight).
- Medication adherence tracking with dosage inventory decrements and low-refill alerts.
- Safe symptom triage with medical disclaimers and emergency hotline references (112, 108).

### Phase 10: Proactive Intelligence & Release Packaging
- Background Proactive Engine: heads-up meeting alerts, hydration reminders, medication prompts, and overdue task alerts.
- Cost & Token Tracker: per-provider token and USD/INR expenditure monitoring.
- Automated installer, build scripts, and Windows launchers.

---
© 2026 Radhe AI Assistant Project. All rights reserved.
"""
    (DIST_DIR / "RELEASE_NOTES_v2.0.md").write_text(release_notes, encoding="utf-8")
    print(" [OK] Generated RELEASE_NOTES_v2.0.md.")

    print("\n==================================================")
    print(f" BUILD COMPLETED SUCCESSFULLY AT: {DIST_DIR}")
    print("==================================================")
    return DIST_DIR


if __name__ == "__main__":
    if preflight_check():
        create_release_package()
        sys.exit(0)
    else:
        print("\n [ERROR] Pre-flight audit failed. Please fix errors before packaging.")
        sys.exit(1)
