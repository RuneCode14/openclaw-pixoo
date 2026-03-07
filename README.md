# OpenClaw-Pixoo

Arcade-style agent activity display for the Divoom Pixoo-64 LED panel.

Shows real-time AI agent status: what it's thinking, which tools it's using, context usage, token counts, and a scrolling activity pulse.

![Layout](docs/layout.png)

## Features

- **Activity Icons** — Thinking, Tool, Web, Cron, Dev — light up in neon colors when active
- **Stats Bars** — Context usage (CTX), total tokens (TOK), model name (LLM), version (VER)
- **Scrolling Pulse** — Activity history bar chart that grows with agent work and decays when idle
- **Live Monitoring** — Watches OpenClaw session logs and updates the display in real-time
- **Pixel Art Renderer** — Custom 3x5 and 4x5 bitmap fonts, 8x8 icons, all rendered in code

## Requirements

- Python 3.8+
- Divoom Pixoo-64 on the same network
- `curl` (for HTTP communication with the Pixoo)
- `nmap` (optional, for device discovery)
- No pip dependencies — uses only Python stdlib

## Quick Start

### 1. Find your Pixoo

```bash
# Auto-detect Pixoo on your network
./scripts/find-pixoo.sh

# Or specify a subnet
./scripts/find-pixoo.sh 192.168.1.0/24
```

The script scans your local network for Divoom devices and reports their IP, current channel, and brightness.

### 2. Test with a single frame

```bash
python3 pixoo_display.py 192.168.178.190 RUNE "#FF3030"
```

### 3. Start the live monitor

```bash
python3 activity_monitor.py --name RUNE --color "#FF3030" --ip 192.168.178.190
```

### 4. Run the demo

```bash
python3 activity_monitor.py --demo
```

## Activity Icons

The display shows five activity indicators. Each lights up in a distinct neon color when the corresponding activity is detected in OpenClaw's session logs:

| Icon | Label | Color | Lights up when... |
|------|-------|-------|-------------------|
| 🧠 | **THK** | Cyan | The LLM is generating a response (thinking/reasoning) |
| 🔧 | **TL** | Yellow | A tool is being executed (`exec`, `Read`, `Write`, `Edit`, `process`) |
| 🌐 | **WEB** | Green | Web tools are active (`web_search`, `web_fetch`, `browser`) |
| ⏰ | **CRN** | Magenta | A heartbeat/cron job is running (scheduled tasks, reminders) |
| 💻 | **DEV** | Orange | Code is being written or edited (file writes to `.py`, `.ts`, `.js`, `.yml`, etc.) |

Icons dim to ~15% brightness when inactive and glow with a border effect when active. Multiple icons can be lit simultaneously (e.g., thinking + tool + web during a complex operation).

### Detection Patterns

The monitor watches OpenClaw session log files (`.jsonl`) for patterns:

- **Thinking**: Model API calls, assistant responses
- **Tool**: `exec`, `Read`, `Write`, `Edit`, `process` tool invocations
- **Web**: `web_search`, `web_fetch`, `browser` tool calls
- **Cron**: Heartbeat messages, scheduled reminders, cron-triggered sessions
- **Dev**: File writes to code files, `git commit`, `git push`, `npm run`, build commands

Each activity has a **5-second decay** — the icon stays lit for 5 seconds after the last matching log entry, then fades out.

## Stats Bars

| Row | Label | Shows |
|-----|-------|-------|
| 1 | **CTX** | Context window usage as percentage (green → yellow → orange → red as it fills) |
| 2 | **TOK** | Total tokens used this session in thousands (e.g., "130K") |
| 3 | **LLM** | Current model name (e.g., "opus-4-6") |
| 4 | **VER** | Software version |

Stats are refreshed from `openclaw status --json` every 30 seconds (configurable with `--stats-interval`).

## Scrolling Pulse

The bottom row shows a scrolling bar chart of recent activity intensity:
- **Bar height** = number of simultaneously active indicators (more activity = taller bars)
- Bars **decay over time** with randomized fade-out
- Scrolls left-to-right as new activity is recorded
- Shows a dim baseline when idle

## Monitor Options

```
--ip IP            Pixoo IP address (default: 192.168.178.190)
--name NAME        Agent name displayed in title bar
--color HEX        Agent color as hex (e.g. "#FF3030" for red)
--interval SECS    Update interval in seconds (default: 1.0)
--brightness 0-100 Display brightness (default: 80)
--stats-interval S How often to refresh stats from OpenClaw (default: 30)
--log-dir PATH     OpenClaw session log directory
--demo             Run in demo mode (cycles through activity states)
```

## Multi-Agent Setup

Run one monitor per agent host, each with a different name and color:

```bash
# On Rune (red)
python3 activity_monitor.py --name RUNE --color "#FF3030"

# On Colossus (green)
python3 activity_monitor.py --name COLOSSUS --color "#30FF30"
```

## Running as a systemd Service

Install as a user service so it starts automatically on login:

```bash
# Copy the service file
cp openclaw-pixoo.service ~/.config/systemd/user/

# Edit it to match your setup (agent name, color, Pixoo IP)
nano ~/.config/systemd/user/openclaw-pixoo.service

# Enable and start
systemctl --user daemon-reload
systemctl --user enable openclaw-pixoo.service
systemctl --user start openclaw-pixoo.service

# Check status
systemctl --user status openclaw-pixoo.service

# View logs
journalctl --user -u openclaw-pixoo.service -f
```

To keep the service running even when you're not logged in:

```bash
sudo loginctl enable-linger $USER
```

### Service Configuration

Edit `~/.config/systemd/user/openclaw-pixoo.service` and adjust the `ExecStart` line:

```ini
ExecStart=/usr/bin/python3 -u %h/path/to/activity_monitor.py \
    --name YOUR_AGENT \
    --color "#FF3030" \
    --ip YOUR_PIXOO_IP \
    --brightness 80
```

## Display Layout (64×64)

```
┌────────────────────────────────────┐
│           RUNE (title)             │  y=0-8    Title bar (agent color)
├╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┤  y=9      Separator
│  🧠  🔧  🌐  ⏰  💻  (icons)     │  y=12-19  Activity icons (8×8 px)
│  THK  TL  WEB CRN DEV (labels)    │  y=21-25  Labels (3×5 font)
├╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┤  y=27     Separator
│  CTX [████████░░░░] 72%            │  y=29     Context usage
│  TOK [██████░░░░░░] 130K           │  y=34     Token count
│  LLM opus-4-6                      │  y=39     Model name
│  VER 2026.3.2                      │  y=45     Version
│                                    │
│  ▁▃▅▇▅▃▁ ▁▃▅▃▁  (pulse)           │  y=56     Activity pulse
└────────────────────────────────────┘
```

## Finding the Pixoo (for AI Agents)

If you're an AI agent setting this up, here's how to find the Pixoo on the network:

```bash
# Option 1: Use the discovery script
./scripts/find-pixoo.sh

# Option 2: Manual probe
# The Pixoo runs an HTTP API on port 80. Scan and probe:
for ip in $(nmap -sn 192.168.1.0/24 -T4 | grep -oP '\d+\.\d+\.\d+\.\d+'); do
    response=$(curl -s -m 1 -X POST "http://$ip:80/post" \
        -H 'Content-Type: application/json' \
        -d '{"Command":"Channel/GetIndex"}' 2>/dev/null)
    if echo "$response" | grep -q '"error_code"'; then
        echo "Pixoo found at: $ip"
    fi
done

# Option 3: Check the Divoom app on a phone connected to the same network
```

**Verification**: Once you have the IP, confirm it's a Pixoo:

```bash
# Should return: Hello World divoom!
curl -s http://PIXOO_IP:80/get

# Should return JSON with error_code: 0
curl -s -X POST http://PIXOO_IP:80/post \
    -H 'Content-Type: application/json' \
    -d '{"Command":"Channel/GetAllConf"}'
```

## Pixoo HTTP API Notes

**Critical: Sequential PicIDs required.** The Pixoo silently ignores frames with non-sequential PicIDs. Always query `Draw/GetHttpGifId` first, then send with `current_id + 1`.

```python
# ✅ Correct
current = query("Draw/GetHttpGifId")["PicId"]
send(PicID=current + 1)

# ❌ Wrong — frame accepted but silently not displayed
send(PicID=1)
send(PicID=random())
```

**Other gotchas:**
- `Draw/ResetHttpGifId` **crashes the Pixoo firmware** — never use it
- Channel 3 is the custom/API draw channel (`Channel/SetIndex` with `SelectIndex: 3`)
- Use `curl` subprocess for HTTP — Python's `urllib` silently fails on large payloads
- The Pixoo persists the last frame to flash (survives reboots)
- Re-assert `Channel/SetIndex` periodically (~30s) if the Pixoo auto-reverts to its clock face
- All API responses return `{"error_code": 0}` even when the frame is silently dropped

## License

MIT
