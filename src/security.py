# security.py
"""
Radhe Security & Cryptography Module.

Provides:
- AES-256-GCM encrypted vault for BYOK API keys and sensitive tokens.
- PBKDF2-HMAC-SHA256 key derivation with persistent salt and device-bound seed.
- Secret masking utilities for logs and API responses.
- Cryptographically chained, tamper-evident audit logger.
"""

import os
import sys
import json
import base64
import hashlib
import logging
import platform
import getpass
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import DATA_DIR

logger = logging.getLogger("Radhe_Security")
logger.setLevel(logging.INFO)

VAULT_FILE = DATA_DIR / "vault.enc"
DEVICE_SECRET_FILE = DATA_DIR / ".device_secret"
AUDIT_LOG_FILE = DATA_DIR / "audit_log.jsonl"
_vault_lock = threading.Lock()
_audit_lock = threading.Lock()


# =====================================================================
# SECRET MASKING UTILITY
# =====================================================================

def mask_secret(secret: Optional[str], show_prefix: int = 3, show_suffix: int = 4) -> str:
    """
    Mask a sensitive string (such as an API key) for safe display.
    Example: 'sk-proj-abc12345xyz9876' -> 'sk-...9876'
    """
    if not secret:
        return ""
    s = str(secret).strip()
    if len(s) <= (show_prefix + show_suffix + 2):
        return "***"
    return f"{s[:show_prefix]}...{s[-show_suffix:]}"


# =====================================================================
# ENCRYPTED SECRET VAULT (AES-256-GCM)
# =====================================================================

class SecretVault:
    """
    Encrypted key-value store using AES-256-GCM with PBKDF2-derived keys.
    Stores secrets in data/vault.enc in encrypted binary envelope.
    """

    def __init__(self, vault_path: Path = VAULT_FILE, master_password: Optional[str] = None):
        self.vault_path = Path(vault_path)
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self._master_password = master_password or os.environ.get("RADHE_MASTER_KEY")
        self._cache: Dict[str, str] = {}
        self._loaded: bool = False

    def _get_device_seed(self) -> bytes:
        """Retrieve or initialize persistent device-bound secret."""
        if not DEVICE_SECRET_FILE.exists():
            DEVICE_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
            new_seed = os.urandom(32)
            try:
                DEVICE_SECRET_FILE.write_bytes(new_seed)
            except Exception as e:
                logger.warning("Could not write device secret file: %s", e)
                return hashlib.sha256(f"{platform.node()}-{getpass.getuser()}".encode("utf-8")).digest()
        try:
            return DEVICE_SECRET_FILE.read_bytes()
        except Exception:
            return hashlib.sha256(f"{platform.node()}-{getpass.getuser()}".encode("utf-8")).digest()

    def _derive_key(self, salt: bytes) -> bytes:
        """Derive 256-bit AES key using PBKDF2-HMAC-SHA256."""
        device_seed = self._get_device_seed()
        pass_bytes = (self._master_password or "RADHE_INTERNAL_DEVICE_BOUND_KEY").encode("utf-8")
        combined_seed = hashlib.sha256(pass_bytes + device_seed).digest()

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        return kdf.derive(combined_seed)

    def _load(self) -> Dict[str, str]:
        """Decrypt and load vault contents into memory cache."""
        with _vault_lock:
            if not self.vault_path.exists():
                self._cache = {}
                self._loaded = True
                return self._cache

            try:
                payload = self.vault_path.read_bytes()
                # Envelope format: salt (16 bytes) + nonce (12 bytes) + ciphertext + tag
                if len(payload) < 28:
                    logger.warning("Corrupted vault file, resetting empty cache.")
                    self._cache = {}
                    self._loaded = True
                    return self._cache

                salt = payload[:16]
                nonce = payload[16:28]
                ciphertext = payload[28:]

                key = self._derive_key(salt)
                aesgcm = AESGCM(key)
                decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
                self._cache = json.loads(decrypted_bytes.decode("utf-8"))
                self._loaded = True
                return self._cache
            except Exception as e:
                logger.error("Failed to decrypt vault: %s", e)
                self._cache = {}
                self._loaded = True
                return self._cache

    def _save(self) -> bool:
        """Encrypt and persist memory cache to disk."""
        with _vault_lock:
            try:
                salt = os.urandom(16)
                nonce = os.urandom(12)
                key = self._derive_key(salt)
                aesgcm = AESGCM(key)

                raw_bytes = json.dumps(self._cache).encode("utf-8")
                ciphertext = aesgcm.encrypt(nonce, raw_bytes, None)

                # Write salt + nonce + ciphertext atomically
                envelope = salt + nonce + ciphertext
                temp_path = self.vault_path.with_suffix(".tmp")
                temp_path.write_bytes(envelope)
                temp_path.replace(self.vault_path)
                return True
            except Exception as e:
                logger.error("Failed to save encrypted vault: %s", e)
                return False

    def set_secret(self, key: str, value: str) -> bool:
        """Store or update a secret in encrypted vault."""
        if not self._loaded:
            self._load()
        k = str(key).strip().lower()
        v = str(value).strip()
        self._cache[k] = v
        ok = self._save()
        if ok:
            audit_logger.log_action("vault_secret_set", "user", "success", {"key": k})
        return ok

    def get_secret(self, key: str, default: Optional[str] = None, check_env: bool = True) -> Optional[str]:
        """Retrieve a decrypted secret by key."""
        if not self._loaded:
            self._load()
        k = str(key).strip().lower()
        val = self._cache.get(k)
        if val is None and check_env:
            # Fallback to environment variable if present
            env_val = os.environ.get(k.upper()) or os.environ.get(f"{k.upper()}_API_KEY")
            return env_val or default
        return val if val is not None else default
        return val

    def delete_secret(self, key: str) -> bool:
        """Remove a secret from vault."""
        if not self._loaded:
            self._load()
        k = str(key).strip().lower()
        if k in self._cache:
            del self._cache[k]
            ok = self._save()
            if ok:
                audit_logger.log_action("vault_secret_deleted", "user", "success", {"key": k})
            return ok
        return False

    def list_keys(self) -> List[str]:
        """List stored secret keys (names only, never plaintext secrets)."""
        if not self._loaded:
            self._load()
        return sorted(list(self._cache.keys()))

    def get_masked_map(self) -> Dict[str, str]:
        """Return map of key -> masked value for safe UI rendering."""
        if not self._loaded:
            self._load()
        return {k: mask_secret(v) for k, v in self._cache.items()}


# =====================================================================
# CRYPTOGRAPHICALLY CHAINED AUDIT LOGGER
# =====================================================================

class AuditLogger:
    """
    Append-only tamper-evident audit logger.
    Each entry includes a SHA-256 hash of the previous entry, creating a hash chain.
    """

    def __init__(self, log_path: Path = AUDIT_LOG_FILE):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash = self._get_latest_hash()

    def _get_latest_hash(self) -> str:
        """Find the hash of the last entry in log file."""
        if not self.log_path.exists():
            return "0" * 64
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if not lines:
                    return "0" * 64
                last_line = lines[-1].strip()
                if not last_line:
                    return "0" * 64
                entry = json.loads(last_line)
                return entry.get("entry_hash", "0" * 64)
        except Exception:
            return "0" * 64

    def log_action(self, action: str, actor: str = "system", status: str = "success", details: Optional[Dict[str, Any]] = None) -> str:
        """Append a securely hashed audit entry."""
        with _audit_lock:
            ts = datetime.now(timezone.utc).isoformat()
            safe_details = details or {}
            # Sanitize details to guarantee no unmasked secrets are logged
            sanitized: Dict[str, Any] = {}
            for k, v in safe_details.items():
                if any(sec in k.lower() for sec in ("key", "password", "token", "secret")):
                    sanitized[k] = mask_secret(str(v))
                else:
                    sanitized[k] = v

            raw_str = f"{self._last_hash}|{ts}|{action}|{actor}|{status}|{json.dumps(sanitized, sort_keys=True)}"
            entry_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

            entry = {
                "timestamp": ts,
                "action": action,
                "actor": actor,
                "status": status,
                "details": sanitized,
                "prev_hash": self._last_hash,
                "entry_hash": entry_hash,
            }

            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
                self._last_hash = entry_hash
                return entry_hash
            except Exception as e:
                logger.error("Failed to write audit log entry: %s", e)
                return ""

    def query(self, limit: int = 50, action_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return recent audit entries with optional action filtering."""
        with _audit_lock:
            if not self.log_path.exists():
                return []
            try:
                entries = []
                with open(self.log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        e = json.loads(line)
                        if action_filter and action_filter.lower() not in e.get("action", "").lower():
                            continue
                        entries.append(e)
                return entries[-limit:]
            except Exception as e:
                logger.error("Error reading audit log: %s", e)
                return []

    def verify_integrity(self) -> tuple[bool, int, str]:
        """
        Verify cryptographic integrity of the audit chain from genesis.
        Returns: (is_valid, total_entries_checked, error_message)
        """
        with _audit_lock:
            if not self.log_path.exists():
                return True, 0, "No audit log file exists."
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                prev = "0" * 64
                for i, line in enumerate(lines):
                    e = json.loads(line)
                    if e.get("prev_hash") != prev:
                        return False, i, f"Chain broken at entry index {i}: prev_hash mismatch."
                    expected_raw = f"{e['prev_hash']}|{e['timestamp']}|{e['action']}|{e['actor']}|{e['status']}|{json.dumps(e['details'], sort_keys=True)}"
                    expected_hash = hashlib.sha256(expected_raw.encode("utf-8")).hexdigest()
                    if e.get("entry_hash") != expected_hash:
                        return False, i, f"Tampered entry detected at index {i}: hash recalculation failed."
                    prev = e.get("entry_hash", "")
                return True, len(lines), "Audit trail integrity verified successfully."
            except Exception as e:
                return False, 0, f"Error verifying audit integrity: {e}"


# ── Global instances ──────────────────────────────────────────────────
vault = SecretVault()
audit_logger = AuditLogger()
