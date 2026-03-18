# src/interfaces/flask_server.py
"""
REST API server for Radhe.
Lets mobile apps / Postman / external tools send commands via HTTP.

Endpoints:
    GET  /status          — health check (no auth required)
    POST /command         — send a text command, get a response

Run standalone:
    python -m src.interfaces.flask_server

Or import and run in a background thread from radhe.py:
    from src.interfaces.flask_server import start_flask_server
    start_flask_server()
"""

import os
import logging
import threading
from functools import wraps

from flask import Flask, jsonify, request

from src.command_parser import CommandParser
from src.command_executor import executor

# 🔥 LLM engine — must be imported before any ai_knowledge call
import src.llm_setup  # noqa: F401  (side effect: attaches brain.llm_client)

# ── Optional token auth ───────────────────────────────────────────────
# Set env var RADHE_API_TOKEN to enable.  Leave unset to disable.
API_TOKEN: str = os.environ.get("RADHE_API_TOKEN", "").strip()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(name)s — %(message)s"
)
logger = logging.getLogger("Radhe_Flask")

app    = Flask(__name__)
parser = CommandParser()


# ==================================================================
# AUTH DECORATOR
# ==================================================================

def require_token(f):
    """Enforce Authorization: Bearer <token> when RADHE_API_TOKEN is set."""
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
# ROUTES
# ==================================================================

@app.get("/status")
def status():
    """Health check — no auth required."""
    return jsonify({"status": "running", "message": "Radhe is online."}), 200


@app.post("/command")
@require_token
def command():
    """
    POST /command
    Body  (JSON): { "command": "open YouTube" }
    Returns (JSON): { "response": "Opening YouTube..." }
    """
    # ── Parse body ────────────────────────────────────────────────────
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    text = (data.get("command") or "").strip()

    if not text:
        return jsonify({"error": "'command' field is required and must not be empty."}), 400

    logger.info("Command from %s: %r", request.remote_addr, text)

    # ── Parse → Execute ───────────────────────────────────────────────
    try:
        parsed = parser.parse(text)
        result = executor.execute(parsed, text)
        response_text = result.get("text", "")
        logger.info("Response: %r", response_text)
        return jsonify({"response": response_text}), 200

    except Exception as e:
        logger.exception("Command processing error: %s", e)
        return jsonify({"error": "Internal server error while processing command."}), 500


# ==================================================================
# ERROR HANDLERS
# ==================================================================

@app.errorhandler(404)
def not_found(exc):
    return jsonify({"error": f"Endpoint not found: {request.path}"}), 404


@app.errorhandler(405)
def method_not_allowed(exc):
    return jsonify({
        "error": f"Method '{request.method}' not allowed on {request.path}."
    }), 405


@app.errorhandler(500)
def internal_error(exc):
    logger.exception("Unhandled server error: %s", exc)
    return jsonify({"error": "Internal server error."}), 500


# ==================================================================
# BACKGROUND THREAD HELPER  (call from radhe.py if needed)
# ==================================================================

def start_flask_server(
    host: str  = "0.0.0.0",
    port: int  = 5000,
    debug: bool = False
) -> threading.Thread:
    """
    Start Flask in a background daemon thread so it runs alongside
    the voice loop without blocking it.

    Usage in radhe.py:
        from src.interfaces.flask_server import start_flask_server
        start_flask_server()    # returns immediately
        run()                   # voice loop blocks here
    """
    def _run():
        logger.info(
            "Flask API starting on http://%s:%d  (auth=%s)",
            host, port,
            "enabled" if API_TOKEN else "disabled"
        )
        app.run(host=host, port=port, debug=debug,
                threaded=True, use_reloader=False)

    t = threading.Thread(target=_run, name="RadheFlaskServer", daemon=True)
    t.start()
    logger.info("Flask server thread started.")
    return t


# ==================================================================
# STANDALONE ENTRY POINT
# ==================================================================

if __name__ == "__main__":
    logger.info("Starting Radhe Flask server...")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)