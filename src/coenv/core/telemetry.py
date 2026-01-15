"""
Anonymous telemetry for CoEnv.

Spawns detached background process to send anonymous usage data.
No latency in main CLI thread.
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any


TELEMETRY_ENDPOINT = "https://telemetry.coenv.dev/v1/events"
TELEMETRY_DISABLED_FILE = ".coenv/.no-telemetry"


def is_telemetry_enabled(project_root: str = ".") -> bool:
    """
    Check if telemetry is enabled.

    Telemetry is disabled if:
    - .coenv/.no-telemetry file exists
    - COENV_NO_TELEMETRY env var is set

    Args:
        project_root: Project root directory

    Returns:
        True if telemetry is enabled
    """
    # Check environment variable
    if os.getenv('COENV_NO_TELEMETRY'):
        return False

    # Check opt-out file
    opt_out_file = Path(project_root) / TELEMETRY_DISABLED_FILE
    if opt_out_file.exists():
        return False

    return True


def hash_identifier(value: str) -> str:
    """
    Hash a value for anonymous reporting.

    Args:
        value: Value to hash

    Returns:
        SHA256 hash of the value
    """
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def send_telemetry_background(event_type: str, data: Dict[str, Any], project_root: str = "."):
    """
    Send telemetry in a detached background process.

    This function returns immediately and spawns a background process
    to send the telemetry asynchronously.

    Args:
        event_type: Type of event (e.g., "sync", "status", "doctor")
        data: Event data (will be anonymized)
        project_root: Project root directory
    """
    if not is_telemetry_enabled(project_root):
        return

    # Create telemetry payload
    payload = {
        'event': event_type,
        'timestamp': datetime.now().isoformat(),
        'data': data,
        'version': '0.1.0',
    }

    # Create a small Python script to send the telemetry
    script = f"""
import json
import requests
import sys

payload = {json.dumps(payload)}

try:
    requests.post(
        "{TELEMETRY_ENDPOINT}",
        json=payload,
        timeout=5,
        headers={{'Content-Type': 'application/json'}}
    )
except Exception:
    pass  # Silently fail
"""

    # Spawn detached process
    try:
        # Use subprocess.Popen with detached process
        if sys.platform == 'win32':
            # Windows
            subprocess.Popen(
                [sys.executable, '-c', script],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        else:
            # Unix-like
            subprocess.Popen(
                [sys.executable, '-c', script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
    except Exception:
        # Silently fail - telemetry should never break the main app
        pass


def track_sync(key_count: int, project_root: str = "."):
    """
    Track a sync operation.

    Args:
        key_count: Number of keys synced
        project_root: Project root directory
    """
    send_telemetry_background(
        'sync',
        {
            'key_count': key_count,
        },
        project_root
    )


def track_status(key_count: int, missing_count: int, project_root: str = "."):
    """
    Track a status check.

    Args:
        key_count: Total number of keys
        missing_count: Number of missing keys
        project_root: Project root directory
    """
    send_telemetry_background(
        'status',
        {
            'key_count': key_count,
            'missing_count': missing_count,
        },
        project_root
    )


def track_doctor(keys_added: int, project_root: str = "."):
    """
    Track a doctor operation.

    Args:
        keys_added: Number of keys added
        project_root: Project root directory
    """
    send_telemetry_background(
        'doctor',
        {
            'keys_added': keys_added,
        },
        project_root
    )


def opt_out(project_root: str = "."):
    """
    Opt out of telemetry.

    Creates .coenv/.no-telemetry file.

    Args:
        project_root: Project root directory
    """
    opt_out_file = Path(project_root) / TELEMETRY_DISABLED_FILE
    opt_out_file.parent.mkdir(exist_ok=True)
    opt_out_file.touch()
