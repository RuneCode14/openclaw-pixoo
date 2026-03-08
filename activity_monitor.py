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

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

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

def load_config(config_path: str = None) -> dict:
    """Load config.yml, returning defaults if not found or yaml unavailable."""
    defaults = {
        'pixoo': {'ip': '192.168.178.190', 'port': 80, 'brightness': 80},
        'agent': {'name': 'RUNE', 'color': '#FF3030', 'header_bg': ''},
        'display': {'fps': 2, 'idle_timeout': 30, 'activity_decay': 5},
        'monitor': {'log_dir': '~/.openclaw/agents/main/sessions'},
    }
    if not HAS_YAML:
        return defaults

    # Search paths: explicit arg, script dir, cwd
    search_paths = []
    if config_path:
        search_paths.append(config_path)
    script_dir = Path(__file__).parent
    search_paths += [script_dir / 'config.yml', Path('config.yml')]

    for p in search_paths:
        p = Path(p)
        if p.is_file():
            try:
                with open(p) as f:
                    cfg = yaml.safe_load(f) or {}
                # Merge with defaults
                for section in defaults:
                    if section in cfg:
                        defaults[section].update(cfg[section])
                print(f"[config] Loaded {p}")
                return defaults
            except Exception as e:
                print(f"[config] Error reading {p}: {e}")

    return defaults


def main():
    parser = argparse.ArgumentParser(description='OpenClaw Pixoo Activity Monitor')
    parser.add_argument('--config', default=None, help='Path to config.yml')
    parser.add_argument('--ip', default=None, help='Pixoo IP address')
    parser.add_argument('--name', default=None, help='Agent name')
    parser.add_argument('--color', default=None, help='Agent color (hex)')
    parser.add_argument('--header-bg', default=None, help='Header bar background color (hex)')
    parser.add_argument('--log-dir', default=None, help='OpenClaw session log directory')
    parser.add_argument('--interval', type=float, default=1.0, help='Update interval (seconds)')
    parser.add_argument('--brightness', type=int, default=None, help='Display brightness (0-100)')
    parser.add_argument('--stats-interval', type=int, default=30,
                        help='How often to refresh stats from OpenClaw (seconds)')
    parser.add_argument('--idle-timeout', type=int, default=None,
                        help='Stop updating display after N minutes of inactivity (0=never)')
    parser.add_argument('--demo', action='store_true', help='Run demo mode instead')
    args = parser.parse_args()

    # Load config.yml, then let CLI args override
    cfg = load_config(args.config)
    args.ip = args.ip or cfg['pixoo']['ip']
    args.name = args.name or cfg['agent']['name']
    args.color = args.color or cfg['agent']['color']
    args.header_bg = args.header_bg or cfg['agent'].get('header_bg', '')
    args.log_dir = args.log_dir or cfg['monitor']['log_dir']
    args.brightness = args.brightness if args.brightness is not None else cfg['pixoo']['brightness']
    if args.idle_timeout is None:
        args.idle_timeout = cfg['display'].get('idle_timeout_minutes', 10)

    if args.demo:
        import sys
        sys.argv = ['pixoo_display.py', args.ip, args.name, args.color]
        from pixoo_display import demo
        demo()
        return

    hdr_display = args.header_bg if args.header_bg else "(auto)"
    print(f"╔════════════════════════════════════════╗")
    print(f"║  OpenClaw-Pixoo Activity Monitor       ║")
    print(f"╠════════════════════════════════════════╣")
    print(f"║  Agent:    {args.name:<28}║")
    print(f"║  Color:    {args.color:<28}║")
    print(f"║  Header:   {hdr_display:<28}║")
    print(f"║  Pixoo:    {args.ip:<28}║")
    idle_display = f"{args.idle_timeout}min" if args.idle_timeout > 0 else "off"
    print(f"║  Logs:     {args.log_dir:<28}║")
    print(f"║  Idle off: {idle_display:<28}║")
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

    header_bg = Color.from_hex(args.header_bg) if args.header_bg else None
    state = AgentState(
        name=args.name,
        color=Color.from_hex(args.color),
        header_bg=header_bg,
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
    last_activity_time = time.time()
    display_sleeping = False
    idle_timeout_secs = args.idle_timeout * 60 if args.idle_timeout > 0 else 0
    frames_sent = 0

    while running:
        # Check for activity
        activities = watcher.get_current_state()
        state.activities = activities
        now = time.time()
        is_active = any(activities.values())

        # Track last activity time
        if is_active:
            last_activity_time = now
            if display_sleeping:
                # Wake up — re-init display and resume updates
                print(f"[pixoo] Activity detected, waking display")
                client.initialize(brightness=args.brightness)
                display_sleeping = False

        # Check idle timeout
        if idle_timeout_secs > 0 and not display_sleeping:
            idle_duration = now - last_activity_time
            if idle_duration >= idle_timeout_secs:
                # Send one final idle frame, then stop updating
                print(f"[pixoo] No activity for {args.idle_timeout}min, display sleeping")
                state.activities = {a: False for a in ACTIVITIES}
                frame_data = renderer.render_frame(state)
                client.send_frame(frame_data)
                display_sleeping = True

        if display_sleeping:
            # Sleep longer when idle — just check for new activity every 5s
            time.sleep(5)
            continue

        state.pulse_offset += 1
        state.frame_count += 1

        # Add pulse when active
        if is_active:
            active_count = sum(1 for v in activities.values() if v)
            height = min(7, active_count * 2 + random.randint(0, 2))
            state.add_pulse(height)

        state.decay_pulse()

        # Refresh stats periodically
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
