#!/usr/bin/env python3
"""
OpenClaw Activity Monitor

Watches OpenClaw session logs and translates activity into Pixoo display state.
Runs as a daemon, continuously updating the Pixoo-64 display.

Usage:
    python3 activity_monitor.py --name RUNE --color "#FF3030"
    python3 activity_monitor.py --name COLOSSUS --color "#30FF30"
"""

import os
import sys
import time
import json
import glob
import re
import random
import signal
import argparse
from pathlib import Path

from pixoo_display import (
    PixooClient, FrameRenderer, AgentState, Stats, Color,
    ACTIVITIES, fetch_openclaw_stats
)

# ── Activity Detection Patterns ──────────────────────────────

PATTERNS = {
    'thinking': [
        r'anthropic/',
        r'ollama/',
        r'"role":\s*"assistant"',
        r'model response',
    ],
    'tool': [
        r'"tool":\s*"(exec|Read|Write|Edit|process)',
        r'function_calls',
        r'Tool call',
    ],
    'web': [
        r'"tool":\s*"(web_search|web_fetch|browser)',
        r'web_search',
        r'web_fetch',
    ],
    'cron': [
        r'HEARTBEAT',
        r'heartbeat',
        r'DYNAMIC_HEARTBEAT',
        r'Scheduled reminder',
    ],
    'code': [
        r'"tool":\s*"(Write|Edit)',
        r'\.(py|ts|js|yml|yaml|rs|go|sh)"',
        r'npm run|git (commit|push)',
        r'compile|build',
    ],
}

COMPILED_PATTERNS = {
    activity: [re.compile(p) for p in patterns]
    for activity, patterns in PATTERNS.items()
}


# ── Log Watcher ──────────────────────────────────────────────

class LogWatcher:
    """Watch OpenClaw session logs for activity."""

    def __init__(self, log_dir: str, decay_seconds: float = 5.0):
        self.log_dir = Path(log_dir).expanduser()
        self.file_positions: dict[str, int] = {}
        self.activity_timestamps: dict[str, float] = {a: 0.0 for a in ACTIVITIES}
        self.decay_seconds = decay_seconds

    def find_latest_log(self) -> 'Path | None':
        """Find the most recently modified session log."""
        patterns = [
            self.log_dir / "sessions" / "**" / "*.jsonl",
            self.log_dir / "**" / "*.jsonl",
            self.log_dir / "**" / "*.log",
        ]
        latest = None
        latest_mtime = 0.0
        for pattern in patterns:
            for f in glob.glob(str(pattern), recursive=True):
                try:
                    mtime = os.path.getmtime(f)
                    if mtime > latest_mtime:
                        latest_mtime = mtime
                        latest = Path(f)
                except OSError:
                    pass
        return latest

    def read_new_lines(self, filepath: Path) -> list[str]:
        """Read new lines since last check."""
        str_path = str(filepath)
        try:
            current_size = filepath.stat().st_size
        except OSError:
            return []

        if str_path not in self.file_positions:
            self.file_positions[str_path] = max(0, current_size - 4096)

        if current_size <= self.file_positions[str_path]:
            return []

        lines = []
        try:
            with open(filepath, 'r', errors='replace') as f:
                f.seek(self.file_positions[str_path])
                lines = f.readlines()
                self.file_positions[str_path] = f.tell()
        except OSError:
            pass
        return lines

    def detect_activities(self, lines: list[str]) -> dict[str, bool]:
        """Detect activity types from new log lines."""
        now = time.time()

        for line in lines:
            for activity, patterns in COMPILED_PATTERNS.items():
                for pattern in patterns:
                    if pattern.search(line):
                        self.activity_timestamps[activity] = now
                        break

        return {
            activity: (now - self.activity_timestamps[activity]) < self.decay_seconds
            for activity in ACTIVITIES
        }

    def get_current_state(self) -> dict[str, bool]:
        """Get current activity state by checking logs."""
        log_file = self.find_latest_log()
        if log_file is None:
            return {a: False for a in ACTIVITIES}
        new_lines = self.read_new_lines(log_file)
        return self.detect_activities(new_lines)


# ── Main Loop ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='OpenClaw Pixoo Activity Monitor')
    parser.add_argument('--ip', default='192.168.178.190', help='Pixoo IP address')
    parser.add_argument('--name', default='RUNE', help='Agent name')
    parser.add_argument('--color', default='#FF3030', help='Agent color (hex)')
    parser.add_argument('--log-dir', default='~/.openclaw/agents/main/sessions',
                        help='OpenClaw session log directory')
    parser.add_argument('--interval', type=float, default=1.0, help='Update interval (seconds)')
    parser.add_argument('--brightness', type=int, default=80, help='Display brightness (0-100)')
    parser.add_argument('--stats-interval', type=int, default=30,
                        help='How often to refresh stats from OpenClaw (seconds)')
    parser.add_argument('--demo', action='store_true', help='Run demo mode instead')
    args = parser.parse_args()

    if args.demo:
        from pixoo_display import demo
        demo()
        return

    print(f"╔════════════════════════════════════════╗")
    print(f"║  OpenClaw-Pixoo Activity Monitor       ║")
    print(f"╠════════════════════════════════════════╣")
    print(f"║  Agent:  {args.name:<30}║")
    print(f"║  Color:  {args.color:<30}║")
    print(f"║  Pixoo:  {args.ip:<30}║")
    print(f"║  Logs:   {args.log_dir:<30}║")
    print(f"╚════════════════════════════════════════╝")

    # Initialize
    client = PixooClient(args.ip)
    if not client.initialize(brightness=args.brightness):
        print("[pixoo] ERROR: Cannot reach display. Check IP and power.")
        sys.exit(1)

    renderer = FrameRenderer()
    watcher = LogWatcher(args.log_dir)

    stats = fetch_openclaw_stats()
    print(f"[pixoo] Stats: model={stats.model_name}, ctx={stats.context_percent}%, tok={stats.total_tokens_k}K")

    state = AgentState(
        name=args.name,
        color=Color.from_hex(args.color),
        stats=stats,
    )

    # Graceful shutdown
    running = True
    def signal_handler(sig, frame):
        nonlocal running
        print("\n[pixoo] Shutting down...")
        running = False
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("[pixoo] Monitoring started. Ctrl+C to stop.")
    last_state_key = None
    last_stats_refresh = time.time()
    frames_sent = 0

    while running:
        # Check for activity
        activities = watcher.get_current_state()
        state.activities = activities
        state.pulse_offset += 1
        state.frame_count += 1

        # Add pulse when active
        if state.any_active():
            active_count = sum(1 for v in activities.values() if v)
            height = min(7, active_count * 2 + random.randint(0, 2))
            state.add_pulse(height)

        state.decay_pulse()

        # Refresh stats periodically
        now = time.time()
        if now - last_stats_refresh > args.stats_interval:
            try:
                state.stats = fetch_openclaw_stats()
                last_stats_refresh = now
            except Exception:
                pass

        # Render and send
        state_key = tuple(sorted(activities.items()))
        activity_changed = state_key != last_state_key

        # Always send frames periodically to prevent Pixoo from
        # reverting to its default channel (keep-alive every 5s)
        should_update = (
            activity_changed or
            state.frame_count % 5 == 0  # Keep-alive frame every 5 intervals
        )

        if should_update:
            # Re-set channel periodically to prevent auto-revert to clock
            if state.frame_count % 30 == 0:
                client.set_channel(3)

            frame_data = renderer.render_frame(state)
            ok = client.send_frame(frame_data)
            if ok:
                frames_sent += 1
            else:
                print(f"[pixoo] Frame send FAILED (attempt {frames_sent + 1})")

            active = [a for a, v in activities.items() if v]
            if activity_changed and active:
                print(f"[pixoo] Active: {', '.join(active)} (frame {frames_sent})")
            elif activity_changed and not active:
                print(f"[pixoo] Idle (frame {frames_sent})")

            # Periodic heartbeat log so we know it's alive
            if frames_sent % 20 == 0:
                print(f"[pixoo] Heartbeat: {frames_sent} frames sent, ctx={state.stats.context_percent}%")

            last_state_key = state_key

        time.sleep(args.interval)

    # Show idle frame on exit
    print(f"[pixoo] Sent {frames_sent} frames total.")
    state.activities = {a: False for a in ACTIVITIES}
    frame_data = renderer.render_frame(state)
    client.send_frame(frame_data)
    print("[pixoo] Done.")


if __name__ == '__main__':
    main()
