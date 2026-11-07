from pathlib import Path

# 1. Update calendar_manager.py
cm = Path("src/calendar_manager.py")
content = cm.read_text(encoding="utf-8")

parse_helper = """def _parse_event_time(val: Any) -> Optional[datetime.datetime]:
    if isinstance(val, datetime.datetime):
        return val
    s = str(val).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except Exception:
            pass
    try:
        return datetime.datetime.fromisoformat(s)
    except Exception:
        pass
    return parse_time(s)
"""

if "_parse_event_time" not in content:
    content = content.replace("class CalendarManager:", parse_helper + "\n\nclass CalendarManager:", 1)
    content = content.replace("start_dt = parse_time(start_time)", "start_dt = _parse_event_time(start_time)")
    content = content.replace("end_dt = parse_time(end_time)", "end_dt = _parse_event_time(end_time)")
    content = content.replace("dt_start = parse_time(start_date)", "dt_start = _parse_event_time(start_date)")
    content = content.replace("dt_end = parse_time(end_date)", "dt_end = _parse_event_time(end_date)")
    cm.write_text(content, encoding="utf-8")
    print("Updated calendar_manager.py with robust time parser.")
else:
    print("calendar_manager.py already updated")

# 2. Update daily_briefing.py to accept optional manager overrides
db = Path("src/daily_briefing.py")
dbc = db.read_text(encoding="utf-8")

old_gen = """    def generate_briefing(
        self,
        user_id: str = "default",
        language: str = "en"
    ) -> Dict[str, Any]:"""

new_gen = """    def generate_briefing(
        self,
        user_id: str = "default",
        language: str = "en",
        memory_mgr: Optional[Any] = None,
        calendar_mgr: Optional[Any] = None,
        reminder_mgr: Optional[Any] = None
    ) -> Dict[str, Any]:"""

old_mem_fetch = """        # 1. User Name & Profile
        user_name = "there"
        try:
            from memory import memory_manager
            prof_name = memory_manager.get_profile_value("user_name", user_id=user_id)
            if prof_name:
                user_name = str(prof_name)
        except Exception as e:
            logger.debug("Briefing profile fetch skipped: %s", e)"""

new_mem_fetch = """        # 1. User Name & Profile
        user_name = "there"
        try:
            m_mgr = memory_mgr
            if not m_mgr:
                from memory import memory_manager as m_mgr
            prof_name = m_mgr.get_profile_value("user_name", user_id=user_id)
            if prof_name:
                user_name = str(prof_name)
        except Exception as e:
            logger.debug("Briefing profile fetch skipped: %s", e)"""

if old_gen in dbc:
    dbc = dbc.replace(old_gen, new_gen, 1)
    dbc = dbc.replace(old_mem_fetch, new_mem_fetch, 1)
    db.write_text(dbc, encoding="utf-8")
    print("Updated daily_briefing.py with manager injection support.")
