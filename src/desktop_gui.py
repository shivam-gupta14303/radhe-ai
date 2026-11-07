# desktop_gui.py
"""
Radhe Desktop Application — Native, responsive desktop interface.

Features:
- 6 Modular Sections:
  1. Dashboard: System status, daily briefing, upcoming reminders, unread chats.
  2. Chat & Voice: Interactive chat log, push-to-talk button, voice status indicator.
  3. AI Settings: BYOK key management, provider switching (OpenAI, Claude, Gemini, Groq, Ollama), model picking, live health test.
  4. Memory Manager: View, search, add, edit, delete 7-tier personal memories, export to JSON/Markdown.
  5. WhatsApp Center: Operating mode switch (Monitor / Approval / Auto-Reply), approval queue with Approve/Discard actions.
  6. Calendar & Tasks: Today's agenda, conflict-aware event creation, task checklist with checkboxes.
- Non-blocking background worker threads for all AI and network calls.
- Windows-friendly, zero external binary dependencies (Tkinter / TTK + PIL).
"""

import sys
import os
import threading
import datetime
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

# Ensure src is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog

from command_parser import parser
from command_executor import executor
from ai_providers import ai_provider_manager
from memory import memory_manager
from reminder_manager import default_reminder_manager
from calendar_manager import calendar_manager
from daily_briefing import daily_briefing_manager
from social_media import social_integrator

logger = logging.getLogger("Radhe_DesktopGUI")


class RadheDesktopApp:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Radhe — Personal AI Companion")
        self.root.geometry("1000x700")
        self.root.minsize(850, 600)

        # Style & Colors
        self._setup_styles()

        # Main Layout: Sidebar + Content
        self._build_layout()

        # Default view
        self._show_tab("dashboard")

        # Initial background status load
        self._refresh_dashboard()

    def _setup_styles(self):
        """Configure modern dark theme palette."""
        self.colors = {
            "bg": "#121418",
            "sidebar_bg": "#1a1d24",
            "card_bg": "#1e222a",
            "accent": "#4a76a8",
            "accent_hover": "#5a86b8",
            "success": "#2e7d32",
            "warning": "#e65100",
            "danger": "#c62828",
            "text": "#e0e6ed",
            "text_muted": "#8c9ba5",
            "input_bg": "#282c37",
        }

        self.root.configure(bg=self.colors["bg"])
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Common ttk styling
        self.style.configure(".", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI", 10))
        self.style.configure("Sidebar.TFrame", background=self.colors["sidebar_bg"])
        self.style.configure("Content.TFrame", background=self.colors["bg"])
        self.style.configure("Card.TFrame", background=self.colors["card_bg"], relief="flat")
        self.style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"), foreground=self.colors["text"])
        self.style.configure("Subheader.TLabel", font=("Segoe UI", 11, "bold"), foreground=self.colors["accent"])
        self.style.configure("Muted.TLabel", font=("Segoe UI", 9), foreground=self.colors["text_muted"])

        # Treeview
        self.style.configure(
            "Treeview",
            background=self.colors["input_bg"],
            foreground=self.colors["text"],
            fieldbackground=self.colors["input_bg"],
            rowheight=28
        )
        self.style.map("Treeview", background=[("selected", self.colors["accent"])])

    def _build_layout(self):
        # Sidebar
        self.sidebar = tk.Frame(self.root, bg=self.colors["sidebar_bg"], width=200)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # App Brand Header
        brand_frame = tk.Frame(self.sidebar, bg=self.colors["sidebar_bg"], pady=18)
        brand_frame.pack(fill="x")
        lbl_title = tk.Label(
            brand_frame, text="✨ RADHE", font=("Segoe UI", 16, "bold"),
            bg=self.colors["sidebar_bg"], fg=self.colors["text"]
        )
        lbl_title.pack()
        lbl_sub = tk.Label(
            brand_frame, text="Personal AI Assistant", font=("Segoe UI", 8),
            bg=self.colors["sidebar_bg"], fg=self.colors["text_muted"]
        )
        lbl_sub.pack()

        # Nav Buttons
        self.nav_buttons = {}
        tabs = [
            ("dashboard", "📊 Dashboard"),
            ("chat", "💬 Chat & Voice"),
            ("ai_settings", "🤖 AI Settings"),
            ("memory", "🧠 Memory"),
            ("whatsapp", "📱 WhatsApp"),
            ("calendar", "📅 Calendar & Tasks"),
        ]
        for key, label in tabs:
            btn = tk.Button(
                self.sidebar, text=label, font=("Segoe UI", 10, "bold"),
                anchor="w", padx=16, pady=10, relief="flat",
                bg=self.colors["sidebar_bg"], fg=self.colors["text"],
                activebackground=self.colors["card_bg"], activeforeground=self.colors["text"],
                command=lambda k=key: self._show_tab(k)
            )
            btn.pack(fill="x", pady=2)
            self.nav_buttons[key] = btn

        # Bottom status in sidebar
        status_frame = tk.Frame(self.sidebar, bg=self.colors["sidebar_bg"], pady=12)
        status_frame.pack(side="bottom", fill="x")
        self.lbl_sidebar_ai = tk.Label(
            status_frame, text="AI: Loading...", font=("Segoe UI", 8),
            bg=self.colors["sidebar_bg"], fg=self.colors["text_muted"], anchor="w", padx=12
        )
        self.lbl_sidebar_ai.pack(fill="x")

        # Main content area
        self.content_area = tk.Frame(self.root, bg=self.colors["bg"])
        self.content_area.pack(side="right", fill="both", expand=True, padx=16, pady=16)

        # Frames container
        self.frames = {
            "dashboard": self._build_dashboard_tab(),
            "chat": self._build_chat_tab(),
            "ai_settings": self._build_ai_settings_tab(),
            "memory": self._build_memory_tab(),
            "whatsapp": self._build_whatsapp_tab(),
            "calendar": self._build_calendar_tab(),
        }

    def _show_tab(self, tab_key: str):
        for k, frame in self.frames.items():
            if k == tab_key:
                frame.pack(fill="both", expand=True)
                self.nav_buttons[k].configure(bg=self.colors["card_bg"], fg=self.colors["accent"])
            else:
                frame.pack_forget()
                self.nav_buttons[k].configure(bg=self.colors["sidebar_bg"], fg=self.colors["text"])

        # Auto refresh data on tab switch
        if tab_key == "dashboard":
            self._refresh_dashboard()
        elif tab_key == "ai_settings":
            self._refresh_ai_settings()
        elif tab_key == "memory":
            self._refresh_memory_list()
        elif tab_key == "whatsapp":
            self._refresh_whatsapp_view()
        elif tab_key == "calendar":
            self._refresh_calendar_and_tasks()

    # ==================================================================
    # 1. DASHBOARD TAB
    # ==================================================================

    def _build_dashboard_tab(self) -> tk.Frame:
        frame = tk.Frame(self.content_area, bg=self.colors["bg"])

        # Header
        hdr = tk.Label(frame, text="Today's Overview", font=("Segoe UI", 16, "bold"), bg=self.colors["bg"], fg=self.colors["text"])
        hdr.pack(anchor="w", pady=(0, 12))

        # Briefing Card
        card_briefing = tk.Frame(frame, bg=self.colors["card_bg"], padx=16, pady=14)
        card_briefing.pack(fill="x", pady=6)
        tk.Label(card_briefing, text="🌅 Morning Briefing", font=("Segoe UI", 11, "bold"), bg=self.colors["card_bg"], fg=self.colors["accent"]).pack(anchor="w")
        self.txt_dashboard_briefing = tk.Label(
            card_briefing, text="Loading your daily briefing...", font=("Segoe UI", 10),
            bg=self.colors["card_bg"], fg=self.colors["text"], wraplength=700, justify="left"
        )
        self.txt_dashboard_briefing.pack(anchor="w", pady=(6, 0))

        # Quick Stats Grid
        grid_frame = tk.Frame(frame, bg=self.colors["bg"])
        grid_frame.pack(fill="x", pady=10)

        # AI Status Card
        card_ai = tk.Frame(grid_frame, bg=self.colors["card_bg"], padx=14, pady=12)
        card_ai.pack(side="left", fill="both", expand=True, padx=(0, 6))
        tk.Label(card_ai, text="Active AI Intelligence", font=("Segoe UI", 9), bg=self.colors["card_bg"], fg=self.colors["text_muted"]).pack(anchor="w")
        self.lbl_dash_ai_name = tk.Label(card_ai, text="Groq (LLaMA 3.3)", font=("Segoe UI", 12, "bold"), bg=self.colors["card_bg"], fg=self.colors["text"])
        self.lbl_dash_ai_name.pack(anchor="w", pady=4)

        # WhatsApp Status Card
        card_wa = tk.Frame(grid_frame, bg=self.colors["card_bg"], padx=14, pady=12)
        card_wa.pack(side="left", fill="both", expand=True, padx=6)
        tk.Label(card_wa, text="WhatsApp Operating Mode", font=("Segoe UI", 9), bg=self.colors["card_bg"], fg=self.colors["text_muted"]).pack(anchor="w")
        self.lbl_dash_wa_mode = tk.Label(card_wa, text="Monitor Mode", font=("Segoe UI", 12, "bold"), bg=self.colors["card_bg"], fg=self.colors["text"])
        self.lbl_dash_wa_mode.pack(anchor="w", pady=4)

        # Tasks Card
        card_tasks = tk.Frame(grid_frame, bg=self.colors["card_bg"], padx=14, pady=12)
        card_tasks.pack(side="left", fill="both", expand=True, padx=(6, 0))
        tk.Label(card_tasks, text="Pending Tasks", font=("Segoe UI", 9), bg=self.colors["card_bg"], fg=self.colors["text_muted"]).pack(anchor="w")
        self.lbl_dash_task_count = tk.Label(card_tasks, text="0 Tasks", font=("Segoe UI", 12, "bold"), bg=self.colors["card_bg"], fg=self.colors["text"])
        self.lbl_dash_task_count.pack(anchor="w", pady=4)

        # Reminders & Schedule Split View
        split_frame = tk.Frame(frame, bg=self.colors["bg"])
        split_frame.pack(fill="both", expand=True, pady=6)

        # Upcoming Reminders
        col_rem = tk.Frame(split_frame, bg=self.colors["card_bg"], padx=12, pady=12)
        col_rem.pack(side="left", fill="both", expand=True, padx=(0, 6))
        tk.Label(col_rem, text="⏰ Upcoming Reminders", font=("Segoe UI", 10, "bold"), bg=self.colors["card_bg"], fg=self.colors["accent"]).pack(anchor="w", pady=(0, 6))
        self.txt_dash_reminders = scrolledtext.ScrolledText(col_rem, bg=self.colors["input_bg"], fg=self.colors["text"], font=("Segoe UI", 9), height=8, relief="flat")
        self.txt_dash_reminders.pack(fill="both", expand=True)

        # Today's Agenda
        col_agenda = tk.Frame(split_frame, bg=self.colors["card_bg"], padx=12, pady=12)
        col_agenda.pack(side="right", fill="both", expand=True, padx=(6, 0))
        tk.Label(col_agenda, text="📅 Today's Schedule", font=("Segoe UI", 10, "bold"), bg=self.colors["card_bg"], fg=self.colors["accent"]).pack(anchor="w", pady=(0, 6))
        self.txt_dash_agenda = scrolledtext.ScrolledText(col_agenda, bg=self.colors["input_bg"], fg=self.colors["text"], font=("Segoe UI", 9), height=8, relief="flat")
        self.txt_dash_agenda.pack(fill="both", expand=True)

        return frame

    def _refresh_dashboard(self):
        def _worker():
            briefing = daily_briefing_manager.generate_briefing()
            act_p = ai_provider_manager.get_active_provider_name().capitalize()
            act_m = ai_provider_manager.get_active_model()
            wa_mode = social_integrator.get_mode().capitalize()
            task_sum = default_reminder_manager.get_tasks_summary()
            rems_text = default_reminder_manager.list_reminders()
            agenda_text = calendar_manager.format_agenda_text()

            def _update():
                self.txt_dashboard_briefing.config(text=briefing.get("spoken_text", ""))
                self.lbl_dash_ai_name.config(text=f"{act_p} ({act_m})")
                self.lbl_sidebar_ai.config(text=f"AI: {act_p} • {act_m}")
                self.lbl_dash_wa_mode.config(text=wa_mode)
                self.lbl_dash_task_count.config(text=f"{task_sum.get('pending', 0)} Pending Tasks")

                self.txt_dash_reminders.delete("1.0", tk.END)
                self.txt_dash_reminders.insert(tk.END, rems_text)

                self.txt_dash_agenda.delete("1.0", tk.END)
                self.txt_dash_agenda.insert(tk.END, agenda_text)

            self.root.after(0, _update)

        threading.Thread(target=_worker, daemon=True).start()

    # ==================================================================
    # 2. CHAT & VOICE TAB
    # ==================================================================

    def _build_chat_tab(self) -> tk.Frame:
        frame = tk.Frame(self.content_area, bg=self.colors["bg"])

        # Chat Log
        self.chat_log = scrolledtext.ScrolledText(
            frame, bg=self.colors["card_bg"], fg=self.colors["text"],
            font=("Segoe UI", 10), padx=12, pady=12, wrap="word", relief="flat"
        )
        self.chat_log.pack(fill="both", expand=True, pady=(0, 10))
        self.chat_log.insert(tk.END, "✨ Radhe: Namaste! I am online and ready to assist you.\n\n")

        # Status Bar
        self.lbl_chat_status = tk.Label(frame, text="Ready", font=("Segoe UI", 8), bg=self.colors["bg"], fg=self.colors["text_muted"])
        self.lbl_chat_status.pack(anchor="w", pady=(0, 4))

        # Bottom Input Bar
        input_bar = tk.Frame(frame, bg=self.colors["bg"])
        input_bar.pack(fill="x")

        self.chat_entry = tk.Entry(
            input_bar, bg=self.colors["input_bg"], fg=self.colors["text"],
            font=("Segoe UI", 11), relief="flat", insertbackground=self.colors["text"]
        )
        self.chat_entry.pack(side="left", fill="both", expand=True, padx=(0, 8), ipady=6)
        self.chat_entry.bind("<Return>", lambda e: self._send_chat_message())

        btn_send = tk.Button(
            input_bar, text="Send", font=("Segoe UI", 10, "bold"),
            bg=self.colors["accent"], fg="#ffffff", relief="flat", padx=16,
            command=self._send_chat_message
        )
        btn_send.pack(side="left", padx=(0, 6))

        self.btn_mic = tk.Button(
            input_bar, text="🎤 Voice", font=("Segoe UI", 10, "bold"),
            bg=self.colors["card_bg"], fg=self.colors["text"], relief="flat", padx=14,
            command=self._trigger_voice_listen
        )
        self.btn_mic.pack(side="left")

        return frame

    def _send_chat_message(self):
        text = self.chat_entry.get().strip()
        if not text:
            return
        self.chat_entry.delete(0, tk.END)

        # Append User Message
        self.chat_log.insert(tk.END, f"👤 You: {text}\n")
        self.chat_log.see(tk.END)
        self.lbl_chat_status.config(text="Radhe is thinking...", fg=self.colors["accent"])

        def _worker():
            try:
                parsed = parser.parse(text)
                res = executor.execute(parsed, text)
                reply = res.get("text") or res.get("response") or "I could not generate a response."
            except Exception as e:
                reply = f"Error: {e}"

            def _update():
                self.chat_log.insert(tk.END, f"✨ Radhe: {reply}\n\n")
                self.chat_log.see(tk.END)
                self.lbl_chat_status.config(text="Ready", fg=self.colors["text_muted"])

            self.root.after(0, _update)

        threading.Thread(target=_worker, daemon=True).start()

    def _trigger_voice_listen(self):
        self.lbl_chat_status.config(text="🎤 Listening for voice command...", fg=self.colors["warning"])
        self.btn_mic.config(bg=self.colors["warning"], text="Listening...")

        def _worker():
            try:
                from speech import record_and_transcribe
                text = record_and_transcribe()
            except Exception as e:
                text = ""
                logger.error("Voice input error: %s", e)

            def _update():
                self.btn_mic.config(bg=self.colors["card_bg"], text="🎤 Voice")
                if text:
                    self.chat_entry.delete(0, tk.END)
                    self.chat_entry.insert(0, text)
                    self._send_chat_message()
                else:
                    self.lbl_chat_status.config(text="No speech detected.", fg=self.colors["text_muted"])

            self.root.after(0, _update)

        threading.Thread(target=_worker, daemon=True).start()

    # ==================================================================
    # 3. AI SETTINGS TAB (BYOK)
    # ==================================================================

    def _build_ai_settings_tab(self) -> tk.Frame:
        frame = tk.Frame(self.content_area, bg=self.colors["bg"])

        hdr = tk.Label(frame, text="AI Intelligence & Provider Selection", font=("Segoe UI", 16, "bold"), bg=self.colors["bg"], fg=self.colors["text"])
        hdr.pack(anchor="w", pady=(0, 12))

        card = tk.Frame(frame, bg=self.colors["card_bg"], padx=18, pady=16)
        card.pack(fill="x", pady=6)

        # Provider Selector
        row1 = tk.Frame(card, bg=self.colors["card_bg"])
        row1.pack(fill="x", pady=8)
        tk.Label(row1, text="Primary AI Provider:", width=20, anchor="w", font=("Segoe UI", 10, "bold"), bg=self.colors["card_bg"], fg=self.colors["text"]).pack(side="left")
        self.cb_provider = ttk.Combobox(row1, values=["openai", "anthropic", "gemini", "groq", "ollama"], state="readonly", width=25)
        self.cb_provider.pack(side="left", padx=8)
        self.cb_provider.bind("<<ComboboxSelected>>", self._on_provider_change)

        # Model Selector
        row2 = tk.Frame(card, bg=self.colors["card_bg"])
        row2.pack(fill="x", pady=8)
        tk.Label(row2, text="Selected Model:", width=20, anchor="w", font=("Segoe UI", 10, "bold"), bg=self.colors["card_bg"], fg=self.colors["text"]).pack(side="left")
        self.cb_model = ttk.Combobox(row2, state="readonly", width=35)
        self.cb_model.pack(side="left", padx=8)

        # API Key (BYOK)
        row3 = tk.Frame(card, bg=self.colors["card_bg"])
        row3.pack(fill="x", pady=8)
        tk.Label(row3, text="API Key (BYOK):", width=20, anchor="w", font=("Segoe UI", 10, "bold"), bg=self.colors["card_bg"], fg=self.colors["text"]).pack(side="left")
        self.ent_api_key = tk.Entry(row3, show="•", width=35, bg=self.colors["input_bg"], fg=self.colors["text"], relief="flat", insertbackground=self.colors["text"])
        self.ent_api_key.pack(side="left", padx=8, ipady=4)

        self.btn_show_key = tk.Button(row3, text="👁 Show", font=("Segoe UI", 8), bg=self.colors["input_bg"], fg=self.colors["text"], relief="flat", command=self._toggle_key_visibility)
        self.btn_show_key.pack(side="left", padx=4)

        btn_save_key = tk.Button(row3, text="Save Key", font=("Segoe UI", 9, "bold"), bg=self.colors["accent"], fg="#fff", relief="flat", padx=10, command=self._save_api_key)
        btn_save_key.pack(side="left", padx=6)

        # Action Buttons
        row4 = tk.Frame(card, bg=self.colors["card_bg"])
        row4.pack(fill="x", pady=(16, 4))

        btn_switch = tk.Button(row4, text="Apply & Switch AI", font=("Segoe UI", 10, "bold"), bg=self.colors["success"], fg="#fff", relief="flat", padx=14, pady=6, command=self._apply_ai_switch)
        btn_switch.pack(side="left", padx=(0, 10))

        btn_test = tk.Button(row4, text="Test Connection", font=("Segoe UI", 10, "bold"), bg=self.colors["accent"], fg="#fff", relief="flat", padx=14, pady=6, command=self._test_ai_connection)
        btn_test.pack(side="left", padx=(0, 10))

        self.lbl_ai_test_status = tk.Label(row4, text="", font=("Segoe UI", 9), bg=self.colors["card_bg"])
        self.lbl_ai_test_status.pack(side="left", padx=8)

        # Fallback Toggle Card
        card_fb = tk.Frame(frame, bg=self.colors["card_bg"], padx=18, pady=14)
        card_fb.pack(fill="x", pady=10)
        self.var_fallback = tk.BooleanVar(value=True)
        chk_fb = tk.Checkbutton(
            card_fb, text="Enable Automatic Fallback (Switches to local Ollama if Cloud AI fails)",
            variable=self.var_fallback, font=("Segoe UI", 10), bg=self.colors["card_bg"],
            fg=self.colors["text"], selectcolor=self.colors["input_bg"], activebackground=self.colors["card_bg"]
        )
        chk_fb.pack(anchor="w")

        return frame

    def _toggle_key_visibility(self):
        if self.ent_api_key.cget("show") == "•":
            self.ent_api_key.config(show="")
            self.btn_show_key.config(text="🙈 Hide")
        else:
            self.ent_api_key.config(show="•")
            self.btn_show_key.config(text="👁 Show")

    def _refresh_ai_settings(self):
        active_p = ai_provider_manager.get_active_provider_name()
        self.cb_provider.set(active_p)
        self._on_provider_change()

    def _on_provider_change(self, event=None):
        selected = self.cb_provider.get()
        prov = ai_provider_manager.providers.get(selected)
        if prov:
            models = prov.list_supported_models()
            self.cb_model.config(values=models)
            self.cb_model.set(prov.get_selected_model())
            # Masked key
            k = prov.get_api_key()
            self.ent_api_key.delete(0, tk.END)
            if k:
                self.ent_api_key.insert(0, k)

    def _save_api_key(self):
        p = self.cb_provider.get()
        key = self.ent_api_key.get().strip()
        ok, msg = ai_provider_manager.set_api_key(p, key)
        if ok:
            messagebox.showinfo("Success", msg)
        else:
            messagebox.showerror("Error", msg)

    def _apply_ai_switch(self):
        p = self.cb_provider.get()
        m = self.cb_model.get()
        ok, msg = ai_provider_manager.set_active_provider(p, m)
        if ok:
            messagebox.showinfo("AI Switched", msg)
            self._refresh_dashboard()
        else:
            messagebox.showerror("Failed", msg)

    def _test_ai_connection(self):
        p = self.cb_provider.get()
        self.lbl_ai_test_status.config(text="Testing connection...", fg=self.colors["accent"])

        def _worker():
            res = ai_provider_manager.test_provider(p)
            status = res.get("status", "error")
            lat = res.get("latency_ms", 0)

            def _update():
                if status == "connected":
                    self.lbl_ai_test_status.config(text=f"Connected ({lat}ms)", fg=self.colors["success"])
                else:
                    self.lbl_ai_test_status.config(text=f"Failed: {res.get('message', '')}", fg=self.colors["danger"])

            self.root.after(0, _update)

        threading.Thread(target=_worker, daemon=True).start()

    # ==================================================================
    # 4. MEMORY MANAGER TAB
    # ==================================================================

    def _build_memory_tab(self) -> tk.Frame:
        frame = tk.Frame(self.content_area, bg=self.colors["bg"])

        # Header & Actions
        hdr_frame = tk.Frame(frame, bg=self.colors["bg"])
        hdr_frame.pack(fill="x", pady=(0, 10))

        tk.Label(hdr_frame, text="Personal Memory Dashboard", font=("Segoe UI", 16, "bold"), bg=self.colors["bg"], fg=self.colors["text"]).pack(side="left")

        btn_export = tk.Button(hdr_frame, text="💾 Export Data", font=("Segoe UI", 9, "bold"), bg=self.colors["accent"], fg="#fff", relief="flat", padx=10, command=self._export_memory)
        btn_export.pack(side="right", padx=4)

        btn_add = tk.Button(hdr_frame, text="➕ Add Memory", font=("Segoe UI", 9, "bold"), bg=self.colors["success"], fg="#fff", relief="flat", padx=10, command=self._manual_add_memory)
        btn_add.pack(side="right", padx=4)

        # Search Bar
        search_frame = tk.Frame(frame, bg=self.colors["card_bg"], padx=10, pady=8)
        search_frame.pack(fill="x", pady=(0, 10))

        tk.Label(search_frame, text="🔍 Search:", bg=self.colors["card_bg"], fg=self.colors["text"]).pack(side="left", padx=4)
        self.ent_mem_search = tk.Entry(search_frame, bg=self.colors["input_bg"], fg=self.colors["text"], relief="flat", font=("Segoe UI", 10))
        self.ent_mem_search.pack(side="left", fill="x", expand=True, padx=6, ipady=3)
        self.ent_mem_search.bind("<KeyRelease>", lambda e: self._refresh_memory_list())

        # Memory Treeview
        tree_frame = tk.Frame(frame, bg=self.colors["card_bg"])
        tree_frame.pack(fill="both", expand=True)

        cols = ("id", "type", "text", "timestamp", "status")
        self.mem_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.mem_tree.heading("id", text="ID")
        self.mem_tree.heading("type", text="Category")
        self.mem_tree.heading("text", text="Memory Content")
        self.mem_tree.heading("timestamp", text="Recorded At")
        self.mem_tree.heading("status", text="Status")

        self.mem_tree.column("id", width=40, anchor="center")
        self.mem_tree.column("type", width=110, anchor="center")
        self.mem_tree.column("text", width=420)
        self.mem_tree.column("timestamp", width=140, anchor="center")
        self.mem_tree.column("status", width=80, anchor="center")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.mem_tree.yview)
        self.mem_tree.configure(yscrollcommand=scrollbar.set)
        self.mem_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Action Buttons
        bot_bar = tk.Frame(frame, bg=self.colors["bg"])
        bot_bar.pack(fill="x", pady=10)

        btn_del = tk.Button(bot_bar, text="Delete Selected", font=("Segoe UI", 9, "bold"), bg=self.colors["danger"], fg="#fff", relief="flat", padx=12, command=self._delete_selected_memory)
        btn_del.pack(side="left", padx=4)

        btn_clear = tk.Button(bot_bar, text="Clear All Memories", font=("Segoe UI", 9), bg=self.colors["card_bg"], fg=self.colors["danger"], relief="flat", padx=12, command=self._clear_all_memories)
        btn_clear.pack(side="right", padx=4)

        return frame

    def _refresh_memory_list(self):
        query = self.ent_mem_search.get().strip()
        memories = memory_manager.search_memories(query=query, limit=100)

        # Clear existing
        for item in self.mem_tree.get_children():
            self.mem_tree.delete(item)

        for m in memories:
            ts = m.get("timestamp", "")[:16].replace("T", " ")
            self.mem_tree.insert("", tk.END, values=(
                m.get("id"),
                m.get("type", "general").upper(),
                m.get("text", ""),
                ts,
                m.get("status", "active")
            ))

    def _manual_add_memory(self):
        fact = simpledialog.askstring("Add Memory", "Enter fact or preference to remember:")
        if fact and fact.strip():
            memory_manager.add_memory(text=fact.strip())
            self._refresh_memory_list()

    def _delete_selected_memory(self):
        selected = self.mem_tree.selection()
        if not selected:
            messagebox.showinfo("Select Memory", "Please select a memory to delete.")
            return
        item = self.mem_tree.item(selected[0])
        mem_id = item["values"][0]
        if messagebox.askyesno("Confirm Delete", f"Delete memory ID {mem_id}?"):
            memory_manager.delete_memory_by_id(mem_id)
            self._refresh_memory_list()

    def _clear_all_memories(self):
        if messagebox.askyesno("Confirm Clear All", "Are you sure you want to delete ALL saved memories?"):
            memory_manager.clear_memories()
            self._refresh_memory_list()

    def _export_memory(self):
        path = memory_manager.export_data(format="json")
        messagebox.showinfo("Export Complete", f"Data exported to:\n{path}")

    # ==================================================================
    # 5. WHATSAPP CENTER TAB
    # ==================================================================

    def _build_whatsapp_tab(self) -> tk.Frame:
        frame = tk.Frame(self.content_area, bg=self.colors["bg"])

        hdr = tk.Label(frame, text="WhatsApp Communication Center", font=("Segoe UI", 16, "bold"), bg=self.colors["bg"], fg=self.colors["text"])
        hdr.pack(anchor="w", pady=(0, 12))

        # Mode Selector Card
        card_mode = tk.Frame(frame, bg=self.colors["card_bg"], padx=18, pady=16)
        card_mode.pack(fill="x", pady=6)
        tk.Label(card_mode, text="Operating Mode:", font=("Segoe UI", 11, "bold"), bg=self.colors["card_bg"], fg=self.colors["accent"]).pack(anchor="w", pady=(0, 8))

        self.wa_mode_var = tk.StringVar(value="monitor")
        modes = [
            ("monitor", "1. Monitor Mode (Reads incoming messages, never replies)"),
            ("approval", "2. Approval Mode (Drafts intelligent reply, asks you before sending)"),
            ("auto_reply", "3. Auto-Reply Mode (Replies automatically using Radhe AI)"),
        ]
        for val, desc in modes:
            rb = tk.Radiobutton(
                card_mode, text=desc, value=val, variable=self.wa_mode_var,
                font=("Segoe UI", 10), bg=self.colors["card_bg"], fg=self.colors["text"],
                selectcolor=self.colors["input_bg"], activebackground=self.colors["card_bg"],
                command=self._on_wa_mode_selected
            )
            rb.pack(anchor="w", pady=4)

        # Pending Approvals Card
        card_appr = tk.Frame(frame, bg=self.colors["card_bg"], padx=18, pady=16)
        card_appr.pack(fill="both", expand=True, pady=10)
        tk.Label(card_appr, text="⏳ Pending Message Approvals", font=("Segoe UI", 11, "bold"), bg=self.colors["card_bg"], fg=self.colors["accent"]).pack(anchor="w", pady=(0, 8))

        self.txt_wa_approvals = scrolledtext.ScrolledText(card_appr, bg=self.colors["input_bg"], fg=self.colors["text"], font=("Segoe UI", 10), height=8, relief="flat")
        self.txt_wa_approvals.pack(fill="both", expand=True, pady=(0, 10))

        btn_row = tk.Frame(card_appr, bg=self.colors["card_bg"])
        btn_row.pack(fill="x")
        btn_refresh = tk.Button(btn_row, text="🔄 Check Messages", font=("Segoe UI", 9, "bold"), bg=self.colors["accent"], fg="#fff", relief="flat", padx=12, command=self._refresh_whatsapp_view)
        btn_refresh.pack(side="left")

        return frame

    def _on_wa_mode_selected(self):
        new_mode = self.wa_mode_var.get()
        msg = social_integrator.set_mode(new_mode)
        messagebox.showinfo("Mode Updated", msg)
        self._refresh_dashboard()

    def _refresh_whatsapp_view(self):
        cur_mode = social_integrator.get_mode()
        self.wa_mode_var.set(cur_mode)
        self.txt_wa_approvals.delete("1.0", tk.END)

        pending = social_integrator.get_pending_approvals()
        if not pending:
            self.txt_wa_approvals.insert(tk.END, "No pending message approvals right now.\nOperating smoothly in " + cur_mode.upper() + " mode.")
        else:
            for p in pending:
                self.txt_wa_approvals.insert(tk.END, f"From: {p.get('contact')}\nMessage: {p.get('incoming')}\nDrafted Reply: {p.get('draft')}\n\n")

    # ==================================================================
    # 6. CALENDAR & TASKS TAB
    # ==================================================================

    def _build_calendar_tab(self) -> tk.Frame:
        frame = tk.Frame(self.content_area, bg=self.colors["bg"])

        # Header
        hdr_frame = tk.Frame(frame, bg=self.colors["bg"])
        hdr_frame.pack(fill="x", pady=(0, 10))
        tk.Label(hdr_frame, text="Schedule, Calendar & Tasks", font=("Segoe UI", 16, "bold"), bg=self.colors["bg"], fg=self.colors["text"]).pack(side="left")

        btn_add_ev = tk.Button(hdr_frame, text="📅 Add Event", font=("Segoe UI", 9, "bold"), bg=self.colors["accent"], fg="#fff", relief="flat", padx=10, command=self._add_calendar_event_dialog)
        btn_add_ev.pack(side="right", padx=4)

        btn_add_t = tk.Button(hdr_frame, text="➕ Add Task", font=("Segoe UI", 9, "bold"), bg=self.colors["success"], fg="#fff", relief="flat", padx=10, command=self._add_task_dialog)
        btn_add_t.pack(side="right", padx=4)

        # Split: Tasks on Left, Agenda on Right
        split = tk.Frame(frame, bg=self.colors["bg"])
        split.pack(fill="both", expand=True)

        # Left: Tasks
        col_tasks = tk.Frame(split, bg=self.colors["card_bg"], padx=14, pady=14)
        col_tasks.pack(side="left", fill="both", expand=True, padx=(0, 6))
        tk.Label(col_tasks, text="To-Do Task List", font=("Segoe UI", 11, "bold"), bg=self.colors["card_bg"], fg=self.colors["accent"]).pack(anchor="w", pady=(0, 8))

        self.task_listbox = tk.Listbox(col_tasks, bg=self.colors["input_bg"], fg=self.colors["text"], font=("Segoe UI", 10), relief="flat", selectmode="single")
        self.task_listbox.pack(fill="both", expand=True, pady=(0, 8))

        btn_done = tk.Button(col_tasks, text="✓ Mark Task Complete", font=("Segoe UI", 9, "bold"), bg=self.colors["success"], fg="#fff", relief="flat", command=self._mark_task_completed)
        btn_done.pack(fill="x")

        # Right: Calendar Agenda
        col_cal = tk.Frame(split, bg=self.colors["card_bg"], padx=14, pady=14)
        col_cal.pack(side="right", fill="both", expand=True, padx=(6, 0))
        tk.Label(col_cal, text="Upcoming Calendar Events", font=("Segoe UI", 11, "bold"), bg=self.colors["card_bg"], fg=self.colors["accent"]).pack(anchor="w", pady=(0, 8))

        self.cal_tree = ttk.Treeview(col_cal, columns=("title", "start", "conflict"), show="headings")
        self.cal_tree.heading("title", text="Event")
        self.cal_tree.heading("start", text="Time")
        self.cal_tree.heading("conflict", text="Conflict")
        self.cal_tree.column("title", width=160)
        self.cal_tree.column("start", width=120, anchor="center")
        self.cal_tree.column("conflict", width=80, anchor="center")
        self.cal_tree.pack(fill="both", expand=True)

        return frame

    def _refresh_calendar_and_tasks(self):
        # Refresh Tasks
        self.task_listbox.delete(0, tk.END)
        self.raw_tasks = default_reminder_manager.list_tasks(status="pending")
        for t in self.raw_tasks:
            self.task_listbox.insert(tk.END, f"[{t['priority'].upper()}] {t['title']}")

        # Refresh Calendar
        for item in self.cal_tree.get_children():
            self.cal_tree.delete(item)
        events = calendar_manager.get_events(limit=20)
        for ev in events:
            t_str = ev.get("start_time", "")[:16].replace("T", " ")
            self.cal_tree.insert("", tk.END, values=(ev.get("title"), t_str, "None"))

    def _add_task_dialog(self):
        title = simpledialog.askstring("Add Task", "Enter task title:")
        if title and title.strip():
            default_reminder_manager.add_task(title=title.strip())
            self._refresh_calendar_and_tasks()

    def _mark_task_completed(self):
        sel = self.task_listbox.curselection()
        if not sel:
            messagebox.showinfo("Select Task", "Please select a task to complete.")
            return
        idx = sel[0]
        task = self.raw_tasks[idx]
        default_reminder_manager.complete_task(task["id"])
        self._refresh_calendar_and_tasks()

    def _add_calendar_event_dialog(self):
        title = simpledialog.askstring("Add Event", "Event Title:")
        if not title:
            return
        time_str = simpledialog.askstring("Event Time", "When? (e.g. tomorrow at 4pm):")
        if not time_str:
            return
        res = calendar_manager.create_event(title, time_str)
        if res.get("success"):
            if res.get("conflicts"):
                messagebox.showwarning("Warning: Conflict Detected", f"Event added, but conflicts with: {res['conflicts'][0]['title']}")
            else:
                messagebox.showinfo("Success", f"Event '{title}' added to calendar.")
            self._refresh_calendar_and_tasks()
        else:
            messagebox.showerror("Error", res.get("error", "Failed to add event"))


def launch_gui():
    """Launch the native desktop interface."""
    root = tk.Tk()
    app = RadheDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
