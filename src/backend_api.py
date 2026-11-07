# backend_api.py
"""
Production FastAPI Backend for Radhe AI Assistant.

Provides high-performance async REST endpoints for:
- System status and health
- Multi-AI Provider management with zero-restart switching & BYOK Vault
- Conversational chat and command execution
- 7-tier memory system CRUD and semantic search
- Task management and reminders
- Calendar events with conflict detection
- WhatsApp Web integration (Monitor / Approval / Auto-Reply & Message Scheduling)
- Cryptographic security audit verification
"""

import os
import sys
import time
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure src on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai_providers import ai_manager
from memory import memory_manager
from reminder_manager import reminder_manager
from calendar_manager import calendar_manager
from daily_briefing import briefing_manager
from social_media import social_integrator
from contact_manager import contact_manager
from security import vault, audit_logger, mask_secret
from health_assistant import health_assistant
from command_parser import parser
from command_executor import CommandExecutor

logger = logging.getLogger("Radhe_FastAPI")
logger.setLevel(logging.INFO)

app = FastAPI(
    title="Radhe AI Assistant API",
    version="2.0.0",
    description="Enterprise REST API for Radhe Personal AI Assistant."
)

# Enable CORS for local dashboards, web UI, and mobile companions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = CommandExecutor()
social_integrator.connect_executor(executor)

RADHE_API_TOKEN = os.environ.get("RADHE_API_TOKEN")


def verify_token(authorization: Optional[str] = Header(None)) -> bool:
    """Optional Bearer token verification if RADHE_API_TOKEN is set."""
    if not RADHE_API_TOKEN:
        return True
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Bearer token")
    token = authorization.split("Bearer ", 1)[1].strip()
    if token != RADHE_API_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid token")
    return True


# =====================================================================
# REQUEST & RESPONSE SCHEMAS
# =====================================================================

class ChatRequest(BaseModel):
    message: str = Field(..., description="User message or voice transcript")
    user_id: str = Field("default", description="User identifier")

class SelectAIRequest(BaseModel):
    provider: str
    model: Optional[str] = None

class SetAPIKeyRequest(BaseModel):
    provider: str
    api_key: str

class FallbackToggleRequest(BaseModel):
    enable_fallback: bool
    fallback_provider: Optional[str] = None

class MemoryAddRequest(BaseModel):
    text: str
    memory_type: Optional[str] = None

class MemoryEditRequest(BaseModel):
    text: str

class TaskCreateRequest(BaseModel):
    title: str
    priority: str = "medium"
    due_date: Optional[str] = None

class CalendarEventRequest(BaseModel):
    title: str
    start_time: str
    end_time: str
    description: str = ""
    location: str = ""

class WhatsAppModeRequest(BaseModel):
    mode: str

class WhatsAppEditDraftRequest(BaseModel):
    new_reply: str

class VitalLogRequest(BaseModel):
    metric: str
    value: float
    unit: Optional[str] = None
    notes: str = ""

class WaterLogRequest(BaseModel):
    amount_ml: float

class MedicationAddRequest(BaseModel):
    name: str
    dosage: str
    schedule_time: str
    instructions: str = ""
    remaining_doses: int = 30

class MedicationTakenRequest(BaseModel):
    medication_name: str

class SymptomTriageRequest(BaseModel):
    symptoms: str
    language: str = "en"

class WhatsAppScheduleRequest(BaseModel):
    recipient: str
    message: str
    time_str: str


# =====================================================================
# ROUTERS
# =====================================================================

api_router = APIRouter(prefix="/api/v1")


# ── 1. STATUS & HEALTH ───────────────────────────────────────────────

@api_router.get("/status")
def get_system_status(_auth: bool = Depends(verify_token)):
    """Return consolidated system telemetry."""
    active_prov = ai_manager.get_active_provider()
    tasks = reminder_manager.list_tasks(status="pending")
    mem_stats = memory_manager.get_stats()
    cal_events = calendar_manager.get_events()
    wa_approvals = social_integrator.get_pending_approvals()

    return {
        "status": "online",
        "system": "Radhe AI Assistant 2.0",
        "ai": {
            "active_provider": ai_manager.active_provider_name,
            "active_model": ai_manager.get_active_model(),
            "connected": bool(active_prov.get_api_key() or active_prov.name == "ollama"),
            "fallback_enabled": ai_manager.enable_fallback,
        },
        "whatsapp": {
            "mode": social_integrator.mode,
            "pending_approvals": len(wa_approvals),
        },
        "tasks": {
            "pending_count": len(tasks),
        },
        "calendar": {
            "total_events": len(cal_events),
        },
        "memory": mem_stats,
    }


# ── 2. CONVERSATIONAL CHAT ──────────────────────────────────────────

@api_router.post("/chat")
def chat_message(req: ChatRequest, _auth: bool = Depends(verify_token)):
    """Process a user message through command parsing or AI provider."""
    t0 = time.time()
    msg = req.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    parsed = parser.parse(msg)
    intent = parsed.get("intent", "unknown")
    routing = parsed.get("routing", "llm")

    # If routing is execute and high confidence, run through executor
    if routing == "execute" and intent != "unknown" and intent != "general_query":
        exec_res = executor.execute(parsed, msg, user_id=req.user_id)
        latency = round((time.time() - t0) * 1000, 2)
        resp_text = exec_res.get("response", "")
        audit_logger.log_action("command_executed", req.user_id, "success", {"intent": intent})
        return {
            "response": resp_text,
            "intent": intent,
            "handled_by": "command_executor",
            "latency_ms": latency,
        }

    # Otherwise route to active AI Provider with 7-tier memory context
    active_prov = ai_manager.get_active_provider()
    memory_context = memory_manager.get_context_prompt()
    system_prompt = f"You are Radhe, a personal AI companion. Be helpful, friendly, natural, and emotionally supportive.\n\n{memory_context}"

    ai_resp = active_prov.generate_reply(msg, system_prompt=system_prompt)
    latency = round((time.time() - t0) * 1000, 2)
    audit_logger.log_action("ai_chat", req.user_id, "success", {"provider": active_prov.name})

    return {
        "response": ai_resp,
        "intent": "general_conversation",
        "handled_by": f"ai_provider:{active_prov.name}",
        "latency_ms": latency,
    }


# ── 3. AI PROVIDER MANAGEMENT (BYOK) ────────────────────────────────

@api_router.get("/ai/providers")
def get_ai_providers(_auth: bool = Depends(verify_token)):
    """List all AI providers with supported models and connection status."""
    return ai_manager.get_all_provider_status()

@api_router.post("/ai/select")
def select_ai_provider(req: SelectAIRequest, _auth: bool = Depends(verify_token)):
    """Switch active provider or model without restarting."""
    ok, msg = ai_manager.set_active_provider(req.provider)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    if req.model:
        ok_m, msg_m = ai_manager.set_provider_model(req.provider, req.model)
        if not ok_m:
            raise HTTPException(status_code=400, detail=msg_m)
    return {"success": True, "message": msg}

@api_router.post("/ai/key")
def set_provider_api_key(req: SetAPIKeyRequest, _auth: bool = Depends(verify_token)):
    """Store BYOK API key securely in encrypted AES-256 vault."""
    ok, msg = ai_manager.set_api_key(req.provider, req.api_key)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@api_router.delete("/ai/key/{provider}")
def delete_provider_api_key(provider: str, _auth: bool = Depends(verify_token)):
    """Remove BYOK API key from encrypted vault."""
    ok, msg = ai_manager.remove_api_key(provider)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@api_router.post("/ai/test/{provider}")
def test_provider_connection(provider: str, _auth: bool = Depends(verify_token)):
    """Run live ping / connectivity check on a provider."""
    return ai_manager.test_provider(provider)

@api_router.post("/ai/fallback")
def toggle_fallback(req: FallbackToggleRequest, _auth: bool = Depends(verify_token)):
    """Configure transparent auto-fallback."""
    ai_manager.enable_fallback = req.enable_fallback
    if req.fallback_provider:
        ai_manager.fallback_provider_name = req.fallback_provider
    ai_manager._save_settings()
    return {"success": True, "enable_fallback": ai_manager.enable_fallback, "fallback_provider": ai_manager.fallback_provider_name}


# ── 4. MEMORY SYSTEM (7-TIER) ───────────────────────────────────────

@api_router.get("/memory")
def get_memories(type: Optional[str] = None, q: Optional[str] = None, _auth: bool = Depends(verify_token)):
    """Search or list memories."""
    if q:
        return memory_manager.search_memories(q, memory_type=type)
    return memory_manager.get_all_memories(memory_type=type)

@api_router.post("/memory")
def add_memory(req: MemoryAddRequest, _auth: bool = Depends(verify_token)):
    """Add a new memory with automatic classification & contradiction resolution."""
    res = memory_manager.add_memory(req.text, memory_type=req.memory_type)
    return res

@api_router.put("/memory/{memory_id}")
def edit_memory(memory_id: int, req: MemoryEditRequest, _auth: bool = Depends(verify_token)):
    """Edit an existing memory record."""
    ok = memory_manager.edit_memory(memory_id, req.text)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found or update failed")
    return {"success": True, "message": "Memory updated successfully"}

@api_router.delete("/memory/{memory_id}")
def delete_memory(memory_id: int, _auth: bool = Depends(verify_token)):
    """Delete a memory record."""
    ok = memory_manager.delete_memory_by_id(memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "message": "Memory deleted successfully"}

@api_router.get("/memory/export")
def export_memories(format: str = Query("json", enum=["json", "markdown"]), _auth: bool = Depends(verify_token)):
    """Export memories in JSON or Markdown format."""
    content = memory_manager.export_memories(format=format)
    return {"format": format, "content": content}


# ── 5. TASKS & REMINDERS ────────────────────────────────────────────

@api_router.get("/tasks")
def list_tasks(status: str = Query("all", enum=["all", "pending", "completed"]), _auth: bool = Depends(verify_token)):
    """List tasks filtered by status."""
    return reminder_manager.list_tasks(status=status)

@api_router.post("/tasks")
def create_task(req: TaskCreateRequest, _auth: bool = Depends(verify_token)):
    """Create a new task."""
    tid = reminder_manager.add_task(req.title, priority=req.priority, due_date=req.due_date)
    return {"success": True, "task_id": tid, "message": f"Task '{req.title}' created."}

@api_router.put("/tasks/{task_id}/complete")
def complete_task(task_id: int, _auth: bool = Depends(verify_token)):
    """Mark a task complete."""
    ok = reminder_manager.complete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "message": f"Task #{task_id} completed."}

@api_router.delete("/tasks/{task_id}")
def delete_task(task_id: int, _auth: bool = Depends(verify_token)):
    """Delete a task."""
    ok = reminder_manager.delete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "message": f"Task #{task_id} deleted."}


# ── 6. CALENDAR INTEGRATION ─────────────────────────────────────────

@api_router.get("/calendar/events")
def list_calendar_events(date: Optional[str] = None, _auth: bool = Depends(verify_token)):
    """List calendar events with optional date filter."""
    return calendar_manager.get_events(date_str=date)

@api_router.post("/calendar/events")
def create_calendar_event(req: CalendarEventRequest, _auth: bool = Depends(verify_token)):
    """Create calendar event with interval conflict detection."""
    conflicts = calendar_manager.check_conflicts(req.start_time, req.end_time)
    eid = calendar_manager.create_event(
        title=req.title,
        start_time=req.start_time,
        end_time=req.end_time,
        description=req.description,
        location=req.location
    )
    return {
        "success": True,
        "event_id": eid,
        "conflicts": conflicts,
        "message": f"Event '{req.title}' created." + (f" Note: {len(conflicts)} conflict(s) detected!" if conflicts else "")
    }

@api_router.delete("/calendar/events/{event_id}")
def delete_calendar_event(event_id: str, _auth: bool = Depends(verify_token)):
    """Delete a calendar event."""
    ok = calendar_manager.delete_event(event_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"success": True, "message": "Event deleted successfully."}


# ── 7. WHATSAPP & SOCIAL MESSAGING ──────────────────────────────────

@api_router.get("/whatsapp/status")
def get_whatsapp_status(_auth: bool = Depends(verify_token)):
    """Get WhatsApp operational mode and connection status."""
    return {
        "mode": social_integrator.mode,
        "pending_approvals": social_integrator.get_pending_approvals()
    }

@api_router.post("/whatsapp/mode")
def set_whatsapp_mode(req: WhatsAppModeRequest, _auth: bool = Depends(verify_token)):
    """Set operational mode (monitor, approval, auto_reply)."""
    msg = social_integrator.set_mode(req.mode)
    return {"success": True, "mode": social_integrator.mode, "message": msg}

@api_router.get("/whatsapp/approvals")
def get_whatsapp_approvals(_auth: bool = Depends(verify_token)):
    """List pending drafts awaiting approval."""
    return social_integrator.get_pending_approvals()

@api_router.post("/whatsapp/approve")
def approve_whatsapp_reply(_auth: bool = Depends(verify_token)):
    """Approve and dispatch pending staged reply."""
    ok, msg = social_integrator.approve_pending_reply()
    return {"success": ok, "message": msg}

@api_router.post("/whatsapp/reject")
def reject_whatsapp_reply(_auth: bool = Depends(verify_token)):
    """Discard pending staged reply."""
    msg = social_integrator.reject_pending_reply()
    return {"success": True, "message": msg}

@api_router.post("/whatsapp/edit")
def edit_whatsapp_reply(req: WhatsAppEditDraftRequest, _auth: bool = Depends(verify_token)):
    """Edit draft text of pending staged reply."""
    msg = social_integrator.edit_pending_reply(req.new_reply)
    return {"success": True, "message": msg}

@api_router.post("/whatsapp/schedule")
def schedule_whatsapp_message(req: WhatsAppScheduleRequest, _auth: bool = Depends(verify_token)):
    """Schedule a WhatsApp message for future delivery."""
    msg = social_integrator.schedule_whatsapp_message(req.recipient, req.message, req.time_str)
    return {"success": "Scheduled" in msg, "message": msg}

@api_router.get("/whatsapp/scheduled")
def list_scheduled_messages(_auth: bool = Depends(verify_token)):
    """List pending scheduled WhatsApp messages."""
    return contact_manager.list_scheduled_messages(status="pending")

@api_router.delete("/whatsapp/scheduled/{msg_id}")
def cancel_scheduled_message(msg_id: int, _auth: bool = Depends(verify_token)):
    """Cancel a pending scheduled message."""
    ok = contact_manager.cancel_scheduled_message(msg_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Scheduled message not found")
    return {"success": True, "message": f"Cancelled scheduled message #{msg_id}."}


# ── 8. DAILY BRIEFING ───────────────────────────────────────────────

@api_router.get("/briefing")
def get_daily_briefing(language: str = Query("hinglish", enum=["hinglish", "en", "hi"]), _auth: bool = Depends(verify_token)):
    """Generate daily morning briefing."""
    briefing = briefing_manager.generate_briefing(language=language)
    return {"language": language, "briefing": briefing}


# ── 9. SECURITY & AUDIT ──────────────────────────────────────────────

@api_router.get("/security/audit")
def query_audit_logs(limit: int = 50, action: Optional[str] = None, _auth: bool = Depends(verify_token)):
    """Query recent security audit entries."""
    return audit_logger.query(limit=limit, action_filter=action)

@api_router.get("/security/verify")
def verify_audit_integrity(_auth: bool = Depends(verify_token)):
    """Verify cryptographic hash chain of audit trail."""
    is_valid, count, msg = audit_logger.verify_integrity()
    return {"valid": is_valid, "entries_checked": count, "message": msg}

@api_router.get("/security/vault")
def list_vault_keys(_auth: bool = Depends(verify_token)):
    """List stored secret keys with masked values."""
    return vault.get_masked_map()


# ── 10. PERSONAL HEALTH ASSISTANT ───────────────────────────────────

@api_router.post("/health/vitals")
def log_health_vital(req: VitalLogRequest, _auth: bool = Depends(verify_token)):
    """Log a vital measurement (sleep, bp, glucose, weight)."""
    vid = health_assistant.log_vital(req.metric, req.value, unit=req.unit, notes=req.notes)
    return {"success": True, "vital_id": vid, "message": f"Logged {req.metric}: {req.value} {req.unit or ''}"}

@api_router.post("/health/water")
def log_water_intake(req: WaterLogRequest, _auth: bool = Depends(verify_token)):
    """Log water intake in ml."""
    total, msg = health_assistant.log_water(req.amount_ml)
    return {"success": True, "today_total_ml": total, "message": msg}

@api_router.get("/health/water")
def get_water_intake(_auth: bool = Depends(verify_token)):
    """Get today's total water intake."""
    total = health_assistant.get_daily_water_total()
    return {"today_total_ml": total, "target_ml": 2500.0}

@api_router.get("/health/summary")
def get_daily_health_summary(date: Optional[str] = None, _auth: bool = Depends(verify_token)):
    """Get complete daily wellness vitals summary."""
    return health_assistant.get_daily_vitals_summary(target_date=date)

@api_router.post("/health/medications")
def add_medication(req: MedicationAddRequest, _auth: bool = Depends(verify_token)):
    """Register a new medication schedule."""
    mid = health_assistant.add_medication(
        req.name, req.dosage, req.schedule_time,
        instructions=req.instructions, remaining_doses=req.remaining_doses
    )
    return {"success": True, "medication_id": mid, "message": f"Medication '{req.name}' registered."}

@api_router.get("/health/medications")
def list_medications(active_only: bool = True, _auth: bool = Depends(verify_token)):
    """List medications."""
    return health_assistant.list_medications(active_only=active_only)

@api_router.post("/health/medications/taken")
def log_medication_taken(req: MedicationTakenRequest, _auth: bool = Depends(verify_token)):
    """Mark medication as taken."""
    ok, msg = health_assistant.log_medication_taken(req.medication_name)
    return {"success": ok, "message": msg}

@api_router.post("/health/triage")
def triage_symptoms(req: SymptomTriageRequest, _auth: bool = Depends(verify_token)):
    """Evaluate symptoms with strict medical disclaimers and emergency detection."""
    return health_assistant.triage_symptoms(req.symptoms, language=req.language)


# ── 11. MOBILE COMPANION SYNC ───────────────────────────────────────

@api_router.get("/mobile/sync")
def sync_companion_state(device_id: str = Query("android_default_device"), _auth: bool = Depends(verify_token)):
    """Sync companion mobile client state."""
    from mobile_bridge import mobile_bridge
    return mobile_bridge.sync_mobile_state(device_id)

@api_router.post("/mobile/register")
def register_companion_device(req: Dict[str, Any], _auth: bool = Depends(verify_token)):
    """Register mobile companion device."""
    from mobile_bridge import mobile_bridge
    return mobile_bridge.register_device(
        device_id=req.get("device_id", "android_default"),
        device_name=req.get("device_name", "Android Phone"),
        platform=req.get("platform", "android"),
        push_token=req.get("push_token"),
        biometric_enabled=req.get("biometric_enabled", True)
    )

app.include_router(api_router)


@app.get("/")
def root():
    return {
        "service": "Radhe AI Assistant API",
        "version": "2.0.0",
        "status": "online",
        "documentation": "/docs",
        "openapi": "/openapi.json"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend_api:app", host="127.0.0.1", port=8000, reload=True)
