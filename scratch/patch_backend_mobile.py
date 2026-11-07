from pathlib import Path

p = Path("src/backend_api.py")
content = p.read_text(encoding="utf-8")

target = "app.include_router(api_router)"
addition = """# ── 11. MOBILE COMPANION SYNC ───────────────────────────────────────

@api_router.get("/mobile/sync")
def sync_companion_state(device_id: str = Query("android_default_device"), _auth: bool = Depends(verify_token)):
    \"\"\"Sync companion mobile client state.\"\"\"
    from mobile_bridge import mobile_bridge
    return mobile_bridge.sync_mobile_state(device_id)

@api_router.post("/mobile/register")
def register_companion_device(req: Dict[str, Any], _auth: bool = Depends(verify_token)):
    \"\"\"Register mobile companion device.\"\"\"
    from mobile_bridge import mobile_bridge
    return mobile_bridge.register_device(
        device_id=req.get("device_id", "android_default"),
        device_name=req.get("device_name", "Android Phone"),
        platform=req.get("platform", "android"),
        push_token=req.get("push_token"),
        biometric_enabled=req.get("biometric_enabled", True)
    )

app.include_router(api_router)"""

if target in content and "/mobile/sync" not in content:
    content = content.replace(target, addition, 1)
    p.write_text(content, encoding="utf-8")
    print("SUCCESS: Added mobile sync endpoints to backend_api.py")
else:
    print("ALREADY PRESENT OR NOT FOUND")
