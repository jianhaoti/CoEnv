"""
Metadata tracking and reporting for CoEnv.

Features:
- Ownership tracking via Git
- Weekly "Friday Pulse" summaries
- Activity logging
"""

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict


@dataclass
class KeyMetadata:
    """Metadata for a single environment variable key."""
    key: str
    owner: str
    created_at: str
    last_modified: str
    last_modified_by: str
    sync_count: int = 0
    source: str = ".env"  # Which file this key came from (e.g., ".env.local")


@dataclass
class ActivityLog:
    """Log entry for sync/save activities."""
    timestamp: str
    action: str  # "sync", "save"
    user: str
    keys_affected: int


class MetadataStore:
    """
    Manages metadata storage and retrieval.

    Metadata is stored in .coenv/metadata.json
    """

    def __init__(self, project_root: str = "."):
        """
        Initialize metadata store.

        Args:
            project_root: Root directory of the project
        """
        self.project_root = Path(project_root)
        self.coenv_dir = self.project_root / ".coenv"
        self.metadata_file = self.coenv_dir / "metadata.json"
        self.activity_log_file = self.coenv_dir / "activity.log"

        # Ensure .coenv directory exists
        self.coenv_dir.mkdir(exist_ok=True)

        # Load existing metadata
        self.keys: Dict[str, KeyMetadata] = self._load_metadata()
        self.activity_log: List[ActivityLog] = self._load_activity_log()

    def _load_metadata(self) -> Dict[str, KeyMetadata]:
        """Load metadata from disk."""
        if not self.metadata_file.exists():
            return {}

        try:
            with open(self.metadata_file, 'r') as f:
                data = json.load(f)
                return {
                    key: KeyMetadata(**meta)
                    for key, meta in data.items()
                }
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_metadata(self):
        """Save metadata to disk."""
        data = {
            key: asdict(meta)
            for key, meta in self.keys.items()
        }

        with open(self.metadata_file, 'w') as f:
            json.dump(data, f, indent=2)

    def _load_activity_log(self) -> List[ActivityLog]:
        """Load activity log from disk."""
        if not self.activity_log_file.exists():
            return []

        try:
            with open(self.activity_log_file, 'r') as f:
                data = json.load(f)
                return [ActivityLog(**entry) for entry in data]
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_activity_log(self):
        """Save activity log to disk."""
        data = [asdict(entry) for entry in self.activity_log]

        with open(self.activity_log_file, 'w') as f:
            json.dump(data, f, indent=2)

    def get_git_user(self) -> str:
        """
        Get current Git user name.

        Returns:
            Git user name or "unknown"
        """
        try:
            result = subprocess.run(
                ['git', 'config', 'user.name'],
                capture_output=True,
                text=True,
                timeout=2,
                cwd=self.project_root
            )
            if result.returncode == 0:
                return result.stdout.strip() or "unknown"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return "unknown"

    def track_key(self, key: str, user: Optional[str] = None, source: str = ".env"):
        """
        Track or update a key's metadata.

        Args:
            key: Environment variable key
            user: User name (defaults to git user)
            source: Source file name (e.g., ".env.local")
        """
        if user is None:
            user = self.get_git_user()

        now = datetime.now().isoformat()

        if key in self.keys:
            # Update existing key
            meta = self.keys[key]
            meta.last_modified = now
            meta.last_modified_by = user
            meta.sync_count += 1
            meta.source = source  # Update source to current file
        else:
            # New key
            self.keys[key] = KeyMetadata(
                key=key,
                owner=user,
                created_at=now,
                last_modified=now,
                last_modified_by=user,
                sync_count=1,
                source=source
            )

        self._save_metadata()

    def log_activity(self, action: str, keys_affected: int, user: Optional[str] = None):
        """
        Log a sync/save action.

        Args:
            action: Type of action ("sync", "save")
            keys_affected: Number of keys affected
            user: User name (defaults to git user)
        """
        if user is None:
            user = self.get_git_user()

        entry = ActivityLog(
            timestamp=datetime.now().isoformat(),
            action=action,
            user=user,
            keys_affected=keys_affected
        )

        self.activity_log.append(entry)
        self._save_activity_log()

    def get_key_metadata(self, key: str) -> Optional[KeyMetadata]:
        """
        Get metadata for a specific key.

        Args:
            key: Environment variable key

        Returns:
            KeyMetadata or None if not found
        """
        return self.keys.get(key)

    def get_weekly_summary(self) -> Dict:
        """
        Get summary of activity for the current week.

        Returns:
            Dictionary with weekly stats
        """
        # Find the most recent Friday
        today = datetime.now()
        days_since_friday = (today.weekday() - 4) % 7  # Friday is 4
        last_friday = today - timedelta(days=days_since_friday)

        # If today is before Friday, go back to previous Friday
        if today.weekday() < 4:
            last_friday -= timedelta(days=7)

        # Set to start of day
        week_start = last_friday.replace(hour=0, minute=0, second=0, microsecond=0)

        # Count activities since week_start
        syncs = 0
        saves = 0
        total_keys = 0
        users = set()

        for entry in self.activity_log:
            entry_time = datetime.fromisoformat(entry.timestamp)
            if entry_time >= week_start:
                users.add(entry.user)
                total_keys += entry.keys_affected

                if entry.action == "sync":
                    syncs += 1
                elif entry.action == "save":
                    saves += 1
        return {
            'week_start': week_start.strftime('%Y-%m-%d'),
            'syncs': syncs,
            'saves': saves,
            'total_keys_affected': total_keys,
            'active_users': list(users),
            'user_count': len(users)
        }

    def should_show_friday_pulse(self) -> bool:
        """
        Check if Friday Pulse should be shown.

        Returns True if:
        - Today is Friday or later in the week
        - Pulse hasn't been shown yet this week
        """
        today = datetime.now()

        # Only show on/after Friday
        if today.weekday() < 4:
            return False

        # Check if we've shown pulse this week
        pulse_marker = self.coenv_dir / ".last_pulse"

        if pulse_marker.exists():
            with open(pulse_marker, 'r') as f:
                last_pulse = datetime.fromisoformat(f.read().strip())

            # If last pulse was this week, don't show again
            days_since_friday = (today.weekday() - 4) % 7
            this_friday = today - timedelta(days=days_since_friday)
            this_friday = this_friday.replace(hour=0, minute=0, second=0, microsecond=0)

            if last_pulse >= this_friday:
                return False

        return True

    def mark_pulse_shown(self):
        """Mark that Friday Pulse has been shown for this week."""
        pulse_marker = self.coenv_dir / ".last_pulse"
        with open(pulse_marker, 'w') as f:
            f.write(datetime.now().isoformat())
