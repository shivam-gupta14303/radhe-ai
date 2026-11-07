from pathlib import Path

p = Path("src/backend_api.py")
content = p.read_text(encoding="utf-8")

# 1. Add import
old_import = "from security import vault, audit_logger, mask_secret"
new_import = """from security import vault, audit_logger, mask_secret
from health_assistant import health_assistant"""

if old_import in content and "health_assistant" not in content:
    content = content.replace(old_import, new_import, 1)

# 2. Add Pydantic models
old_models = "class WhatsAppScheduleRequest(BaseModel):"
new_models = """class VitalLogRequest(BaseModel):
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

class WhatsAppScheduleRequest(BaseModel):"""

if old_models in content and "VitalLogRequest" not in content:
    content = content.replace(old_models, new_models, 1)

# 3. Add Endpoints
old_audit_end = """@api_router.get("/security/vault")
def list_vault_keys(_auth: bool = Depends(verify_token)):
    \"\"\"List stored secret keys with masked values.\"\"\"
    return vault.get_masked_map()"""

new_health_endpoints = """@api_router.get("/security/vault")
def list_vault_keys(_auth: bool = Depends(verify_token)):
    \"\"\"List stored secret keys with masked values.\"\"\"
    return vault.get_masked_map()


# ── 10. PERSONAL HEALTH ASSISTANT ───────────────────────────────────

@api_router.post("/health/vitals")
def log_health_vital(req: VitalLogRequest, _auth: bool = Depends(verify_token)):
    \"\"\"Log a vital measurement (sleep, bp, glucose, weight).\"\"\"
    vid = health_assistant.log_vital(req.metric, req.value, unit=req.unit, notes=req.notes)
    return {"success": True, "vital_id": vid, "message": f"Logged {req.metric}: {req.value} {req.unit or ''}"}

@api_router.post("/health/water")
def log_water_intake(req: WaterLogRequest, _auth: bool = Depends(verify_token)):
    \"\"\"Log water intake in ml.\"\"\"
    total, msg = health_assistant.log_water(req.amount_ml)
    return {"success": True, "today_total_ml": total, "message": msg}

@api_router.get("/health/water")
def get_water_intake(_auth: bool = Depends(verify_token)):
    \"\"\"Get today's total water intake.\"\"\"
    total = health_assistant.get_daily_water_total()
    return {"today_total_ml": total, "target_ml": 2500.0}

@api_router.get("/health/summary")
def get_daily_health_summary(date: Optional[str] = None, _auth: bool = Depends(verify_token)):
    \"\"\"Get complete daily wellness vitals summary.\"\"\"
    return health_assistant.get_daily_vitals_summary(target_date=date)

@api_router.post("/health/medications")
def add_medication(req: MedicationAddRequest, _auth: bool = Depends(verify_token)):
    \"\"\"Register a new medication schedule.\"\"\"
    mid = health_assistant.add_medication(
        req.name, req.dosage, req.schedule_time,
        instructions=req.instructions, remaining_doses=req.remaining_doses
    )
    return {"success": True, "medication_id": mid, "message": f"Medication '{req.name}' registered."}

@api_router.get("/health/medications")
def list_medications(active_only: bool = True, _auth: bool = Depends(verify_token)):
    \"\"\"List medications.\"\"\"
    return health_assistant.list_medications(active_only=active_only)

@api_router.post("/health/medications/taken")
def log_medication_taken(req: MedicationTakenRequest, _auth: bool = Depends(verify_token)):
    \"\"\"Mark medication as taken.\"\"\"
    ok, msg = health_assistant.log_medication_taken(req.medication_name)
    return {"success": ok, "message": msg}

@api_router.post("/health/triage")
def triage_symptoms(req: SymptomTriageRequest, _auth: bool = Depends(verify_token)):
    \"\"\"Evaluate symptoms with strict medical disclaimers and emergency detection.\"\"\"
    return health_assistant.triage_symptoms(req.symptoms, language=req.language)"""

if old_audit_end in content and "/health/vitals" not in content:
    content = content.replace(old_audit_end, new_health_endpoints, 1)

p.write_text(content, encoding="utf-8")
print("SUCCESS: Updated backend_api.py with Health endpoints")
