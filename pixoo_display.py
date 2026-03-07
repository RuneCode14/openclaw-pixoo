#!/usr/bin/env python3
"""
OpenClaw-Pixoo Display Renderer

Renders agent activity state to a Divoom Pixoo-64 (64x64 LED panel).
Arcade-style retro visuals with neon colors on dark background.

Usage:
    python3 pixoo_display.py [IP] [AGENT_NAME] [COLOR_HEX]
    python3 pixoo_display.py 192.168.178.190 RUNE "#FF3030"
    python3 pixoo_display.py 192.168.178.190 COLOSSUS "#30FF30"
"""

import json
import base64
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

# ── Constants ────────────────────────────────────────────────

WIDTH = 64
HEIGHT = 64

# Layout Y positions
TITLE_Y = 0
TITLE_H = 9
SEP1_Y = 9
ICON_Y = 12
ICON_H = 8
LABEL_Y = 21
SEP2_Y = 27
STATS_Y = 29
BAR_HEIGHT = 3
BAR_GAP = 2
PULSE_Y = 56

# ── Colors ───────────────────────────────────────────────────

@dataclass
class Color:
    r: int
    g: int
    b: int

    def dim(self, factor: float = 0.25) -> 'Color':
        return Color(int(self.r * factor), int(self.g * factor), int(self.b * factor))

    def bright(self, factor: float = 1.5) -> 'Color':
        return Color(
            min(255, int(self.r * factor)),
            min(255, int(self.g * factor)),
            min(255, int(self.b * factor))
        )

    def tuple(self) -> tuple:
        return (self.r, self.g, self.b)

    @classmethod
    def from_hex(cls, hex_str: str) -> 'Color':
        hex_str = hex_str.lstrip('#')
        return cls(int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))


# Arcade neon palette
BLACK = Color(0, 0, 0)
DARK_BG = Color(8, 8, 25)
WHITE = Color(255, 255, 255)
GRAY = Color(140, 140, 140)
DIM_GRAY = Color(50, 50, 50)

CYAN = Color(0, 255, 255)
YELLOW = Color(255, 255, 50)
GREEN = Color(50, 255, 120)
MAGENTA = Color(255, 50, 255)
ORANGE = Color(255, 180, 0)
BLUE = Color(80, 160, 255)


def bar_color_for_percent(pct: int) -> Color:
    """Color gradient for progress bars based on fill level."""
    if pct < 50:
        return GREEN
    elif pct < 75:
        return YELLOW
    elif pct < 90:
        return ORANGE
    else:
        return Color(255, 40, 40)


# ── Pixel Fonts ──────────────────────────────────────────────

FONT_4x5 = {
    'A': [0b0110, 0b1001, 0b1111, 0b1001, 0b1001],
    'B': [0b1110, 0b1001, 0b1110, 0b1001, 0b1110],
    'C': [0b0111, 0b1000, 0b1000, 0b1000, 0b0111],
    'D': [0b1110, 0b1001, 0b1001, 0b1001, 0b1110],
    'E': [0b1111, 0b1000, 0b1110, 0b1000, 0b1111],
    'F': [0b1111, 0b1000, 0b1110, 0b1000, 0b1000],
    'G': [0b0111, 0b1000, 0b1011, 0b1001, 0b0110],
    'H': [0b1001, 0b1001, 0b1111, 0b1001, 0b1001],
    'I': [0b1110, 0b0100, 0b0100, 0b0100, 0b1110],
    'J': [0b0111, 0b0010, 0b0010, 0b1010, 0b0100],
    'K': [0b1001, 0b1010, 0b1100, 0b1010, 0b1001],
    'L': [0b1000, 0b1000, 0b1000, 0b1000, 0b1111],
    'M': [0b10001, 0b11011, 0b10101, 0b10001, 0b10001],
    'N': [0b1001, 0b1101, 0b1011, 0b1001, 0b1001],
    'O': [0b0110, 0b1001, 0b1001, 0b1001, 0b0110],
    'P': [0b1110, 0b1001, 0b1110, 0b1000, 0b1000],
    'R': [0b1110, 0b1001, 0b1110, 0b1010, 0b1001],
    'S': [0b0111, 0b1000, 0b0110, 0b0001, 0b1110],
    'T': [0b11111, 0b00100, 0b00100, 0b00100, 0b00100],
    'U': [0b1001, 0b1001, 0b1001, 0b1001, 0b0110],
    'V': [0b1001, 0b1001, 0b1001, 0b0110, 0b0110],
    'W': [0b10001, 0b10001, 0b10101, 0b11011, 0b10001],
    'X': [0b1001, 0b1001, 0b0110, 0b1001, 0b1001],
    'Y': [0b10001, 0b01010, 0b00100, 0b00100, 0b00100],
    'Z': [0b1111, 0b0001, 0b0110, 0b1000, 0b1111],
    '0': [0b0110, 0b1001, 0b1001, 0b1001, 0b0110],
    '1': [0b0100, 0b1100, 0b0100, 0b0100, 0b1110],
    '2': [0b1110, 0b0001, 0b0110, 0b1000, 0b1111],
    '3': [0b1110, 0b0001, 0b0110, 0b0001, 0b1110],
    '4': [0b1001, 0b1001, 0b1111, 0b0001, 0b0001],
    '5': [0b1111, 0b1000, 0b1110, 0b0001, 0b1110],
    '6': [0b0110, 0b1000, 0b1110, 0b1001, 0b0110],
    '7': [0b1111, 0b0001, 0b0010, 0b0100, 0b0100],
    '8': [0b0110, 0b1001, 0b0110, 0b1001, 0b0110],
    '9': [0b0110, 0b1001, 0b0111, 0b0001, 0b0110],
    '.': [0b00, 0b00, 0b00, 0b00, 0b10],
    '-': [0b0000, 0b0000, 0b1111, 0b0000, 0b0000],
    '/': [0b0001, 0b0010, 0b0100, 0b1000, 0b0000],
    '%': [0b1001, 0b0010, 0b0100, 0b1001, 0b0000],
    ' ': [0b0000, 0b0000, 0b0000, 0b0000, 0b0000],
}

FONT_3x5 = {
    'A': [0b010, 0b101, 0b111, 0b101, 0b101],
    'B': [0b110, 0b101, 0b110, 0b101, 0b110],
    'C': [0b011, 0b100, 0b100, 0b100, 0b011],
    'D': [0b110, 0b101, 0b101, 0b101, 0b110],
    'E': [0b111, 0b100, 0b110, 0b100, 0b111],
    'F': [0b111, 0b100, 0b110, 0b100, 0b100],
    'G': [0b011, 0b100, 0b101, 0b101, 0b011],
    'H': [0b101, 0b101, 0b111, 0b101, 0b101],
    'I': [0b111, 0b010, 0b010, 0b010, 0b111],
    'K': [0b101, 0b110, 0b100, 0b110, 0b101],
    'L': [0b100, 0b100, 0b100, 0b100, 0b111],
    'M': [0b101, 0b111, 0b111, 0b101, 0b101],
    'N': [0b101, 0b111, 0b111, 0b101, 0b101],
    'O': [0b010, 0b101, 0b101, 0b101, 0b010],
    'P': [0b110, 0b101, 0b110, 0b100, 0b100],
    'R': [0b110, 0b101, 0b110, 0b110, 0b101],
    'S': [0b011, 0b100, 0b010, 0b001, 0b110],
    'T': [0b111, 0b010, 0b010, 0b010, 0b010],
    'U': [0b101, 0b101, 0b101, 0b101, 0b010],
    'V': [0b101, 0b101, 0b101, 0b101, 0b010],
    'W': [0b101, 0b101, 0b111, 0b111, 0b101],
    'X': [0b101, 0b101, 0b010, 0b101, 0b101],
    ' ': [0b000, 0b000, 0b000, 0b000, 0b000],
    '0': [0b010, 0b101, 0b101, 0b101, 0b010],
    '1': [0b010, 0b110, 0b010, 0b010, 0b111],
    '2': [0b110, 0b001, 0b010, 0b100, 0b111],
    '3': [0b110, 0b001, 0b010, 0b001, 0b110],
    '4': [0b101, 0b101, 0b111, 0b001, 0b001],
    '5': [0b111, 0b100, 0b110, 0b001, 0b110],
    '6': [0b011, 0b100, 0b110, 0b101, 0b010],
    '7': [0b111, 0b001, 0b010, 0b010, 0b010],
    '8': [0b010, 0b101, 0b010, 0b101, 0b010],
    '9': [0b010, 0b101, 0b011, 0b001, 0b110],
    '.': [0b000, 0b000, 0b000, 0b000, 0b010],
    '-': [0b000, 0b000, 0b111, 0b000, 0b000],
    '%': [0b101, 0b001, 0b010, 0b100, 0b101],
    '/': [0b001, 0b001, 0b010, 0b100, 0b100],
    'K': [0b101, 0b110, 0b100, 0b110, 0b101],
}

# ── 8x8 Pixel Art Icons ─────────────────────────────────────

ICON_BRAIN = [
    "  ####  ",
    " ##  ## ",
    "## ## ##",
    "# #### #",
    "# #  # #",
    "## ## ##",
    " ##  ## ",
    "  ####  ",
]

ICON_TOOL = [
    "      ##",
    "     ## ",
    " #  ##  ",
    " # ##   ",
    " ###    ",
    " ##     ",
    "##      ",
    "#       ",
]

ICON_WEB = [
    "  ####  ",
    " # ## # ",
    "# #  # #",
    "########",
    "# #  # #",
    " # ## # ",
    "  ####  ",
    "        ",
]

ICON_CRON = [
    "  ####  ",
    " #    # ",
    "#  #   #",
    "#  #   #",
    "#  ### #",
    "#      #",
    " #    # ",
    "  ####  ",
]

ICON_CODE = [
    "  #  #  ",
    " #    # ",
    "#      #",
    "#      #",
    "#      #",
    " #    # ",
    "  #  #  ",
    "        ",
]

# ── Activity Types ───────────────────────────────────────────

ACTIVITIES = ['thinking', 'tool', 'web', 'cron', 'code']

ACTIVITY_CONFIG = {
    'thinking': {'icon': ICON_BRAIN, 'color': CYAN,    'label': 'THK'},
    'tool':     {'icon': ICON_TOOL,  'color': YELLOW,  'label': 'TL'},
    'web':      {'icon': ICON_WEB,   'color': GREEN,   'label': 'WEB'},
    'cron':     {'icon': ICON_CRON,  'color': MAGENTA, 'label': 'CRN'},
    'code':     {'icon': ICON_CODE,  'color': ORANGE,  'label': 'DEV'},
}


# ── State ────────────────────────────────────────────────────

@dataclass
class Stats:
    """System stats for display."""
    context_percent: int = 0
    context_used_k: int = 0
    context_max_k: int = 200
    total_tokens_k: int = 0     # Total tokens this session in K
    model_name: str = "opus-4"
    version: str = "2026.3"


@dataclass
class AgentState:
    name: str = "RUNE"
    color: Color = field(default_factory=lambda: Color(255, 50, 50))
    header_bg: Optional[Color] = None   # Header bar background; None = auto-derive from color
    activities: dict = field(default_factory=lambda: {a: False for a in ACTIVITIES})
    stats: Stats = field(default_factory=Stats)
    pulse_history: list = field(default_factory=lambda: [0] * WIDTH)
    pulse_offset: int = 0
    frame_count: int = 0

    def set_active(self, activity: str, active: bool = True):
        if activity in self.activities:
            self.activities[activity] = active

    def any_active(self) -> bool:
        return any(self.activities.values())

    def add_pulse(self, height: int):
        """Add a pulse bar at the current write position."""
        idx = self.frame_count % WIDTH
        self.pulse_history[idx] = min(7, max(0, height))

    def decay_pulse(self):
        """Gradually reduce pulse heights."""
        import random
        for i in range(WIDTH):
            if self.pulse_history[i] > 0 and random.random() > 0.7:
                self.pulse_history[i] = max(0, self.pulse_history[i] - 1)


# ── Frame Renderer ───────────────────────────────────────────

class FrameRenderer:
    def __init__(self):
        self.pixels = [[DARK_BG for _ in range(WIDTH)] for _ in range(HEIGHT)]

    def clear(self):
        self.pixels = [[DARK_BG for _ in range(WIDTH)] for _ in range(HEIGHT)]

    def set_pixel(self, x: int, y: int, color: Color):
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            self.pixels[y][x] = color

    def draw_rect(self, x1: int, y1: int, x2: int, y2: int, color: Color):
        for y in range(max(0, y1), min(HEIGHT, y2 + 1)):
            for x in range(max(0, x1), min(WIDTH, x2 + 1)):
                self.pixels[y][x] = color

    def draw_hline(self, y: int, color: Color, dotted: bool = False):
        for x in range(WIDTH):
            if not dotted or x % 2 == 0:
                self.set_pixel(x, y, color)

    def _glyph_width(self, glyph):
        if not glyph:
            return 4
        max_bits = max(glyph)
        return max_bits.bit_length() if max_bits > 0 else 1

    def draw_text_4x5(self, text: str, x: int, y: int, color: Color) -> int:
        cx = x
        for ch in text.upper():
            glyph = FONT_4x5.get(ch)
            if glyph is None:
                cx += 3
                continue
            gw = self._glyph_width(glyph)
            for row_i, row_bits in enumerate(glyph):
                for col_i in range(gw):
                    if row_bits & (1 << (gw - 1 - col_i)):
                        self.set_pixel(cx + col_i, y + row_i, color)
            cx += gw + 1
        return cx - x

    def draw_text_3x5(self, text: str, x: int, y: int, color: Color) -> int:
        cx = x
        for ch in text.upper():
            glyph = FONT_3x5.get(ch)
            if glyph is None:
                cx += 3
                continue
            for row_i, row_bits in enumerate(glyph):
                for col_i in range(3):
                    if row_bits & (1 << (2 - col_i)):
                        self.set_pixel(cx + col_i, y + row_i, color)
            cx += 4
        return cx - x

    def text_width_4x5(self, text: str) -> int:
        w = 0
        for ch in text.upper():
            glyph = FONT_4x5.get(ch)
            if glyph is None:
                w += 3
            else:
                w += self._glyph_width(glyph) + 1
        return max(0, w - 1)

    def draw_icon(self, icon: list, x: int, y: int, color: Color):
        for row_i, row in enumerate(icon):
            for col_i, ch in enumerate(row):
                if ch == '#':
                    self.set_pixel(x + col_i, y + row_i, color)

    # ── Section Renderers ────────────────────────────────────

    def draw_title_bar(self, state: AgentState):
        agent_color = state.color
        bg = state.header_bg if state.header_bg else agent_color.dim(0.25)
        border = state.header_bg.bright(1.5) if state.header_bg else agent_color.dim(0.5)
        self.draw_rect(0, TITLE_Y, WIDTH - 1, TITLE_Y + TITLE_H - 1, bg)
        self.draw_hline(TITLE_Y, border)
        self.draw_hline(TITLE_Y + TITLE_H - 1, border)
        tw = self.text_width_4x5(state.name)
        sx = (WIDTH - tw) // 2
        self.draw_text_4x5(state.name, sx, TITLE_Y + 2, WHITE)

    def draw_activity_icons(self, state: AgentState):
        num = len(ACTIVITIES)
        total_w = num * ICON_H + (num - 1) * 4
        sx = (WIDTH - total_w) // 2

        for i, activity in enumerate(ACTIVITIES):
            cfg = ACTIVITY_CONFIG[activity]
            is_active = state.activities[activity]
            color = cfg['color'] if is_active else cfg['color'].dim(0.15)
            ix = sx + i * (ICON_H + 4)

            self.draw_icon(cfg['icon'], ix, ICON_Y, color)

            # Glow border when active
            if is_active:
                glow = cfg['color'].dim(0.3)
                for dx in [-1, ICON_H]:
                    for dy in range(ICON_H):
                        self.set_pixel(ix + dx, ICON_Y + dy, glow)
                for dy in [-1, ICON_H]:
                    for dx in range(ICON_H):
                        self.set_pixel(ix + dx, ICON_Y + dy, glow)

            # Label — bright when active, visible when idle
            label = cfg['label']
            label_w = len(label) * 4 - 1
            lx = ix + (ICON_H - label_w) // 2
            lc = cfg['color'] if is_active else cfg['color'].dim(0.3)
            self.draw_text_3x5(label, lx, LABEL_Y, lc)

    def draw_stats(self, state: AgentState):
        stats = state.stats
        y = STATS_Y
        bar_x, bar_w = 15, 34

        # CTX bar
        self.draw_text_3x5('CTX', 1, y, GRAY)
        self.draw_rect(bar_x, y, bar_x + bar_w - 1, y + BAR_HEIGHT - 1, DIM_GRAY)
        fill_w = max(1, int(bar_w * stats.context_percent / 100))
        fc = bar_color_for_percent(stats.context_percent)
        self.draw_rect(bar_x, y, bar_x + fill_w - 1, y + BAR_HEIGHT - 1, fc)
        self.draw_text_3x5(f'{stats.context_percent}%', 51, y, fc)

        y += BAR_HEIGHT + BAR_GAP

        # TOK bar — total tokens vs context max
        tok_k = stats.total_tokens_k
        tok_pct = min(100, int(tok_k / max(1, stats.context_max_k) * 100))
        self.draw_text_3x5('TOK', 1, y, GRAY)
        self.draw_rect(bar_x, y, bar_x + bar_w - 1, y + BAR_HEIGHT - 1, DIM_GRAY)
        if tok_pct > 0:
            tf = max(1, int(bar_w * tok_pct / 100))
            self.draw_rect(bar_x, y, bar_x + tf - 1, y + BAR_HEIGHT - 1, BLUE)
        self.draw_text_3x5(f'{tok_k}K', 51, y, BLUE)

        y += BAR_HEIGHT + BAR_GAP

        # LLM
        self.draw_text_3x5('LLM', 1, y, GRAY)
        self.draw_text_3x5(stats.model_name[:10], 15, y, Color(0, 200, 200))

        y += 6

        # VER
        self.draw_text_3x5('VER', 1, y, GRAY)
        self.draw_text_3x5(stats.version, 15, y, Color(200, 200, 200))

    def draw_pulse_line(self, state: AgentState):
        """Scrolling activity pulse — bar chart, height = token activity."""
        agent_color = state.color
        base_y = PULSE_Y
        offset = state.pulse_offset

        for x in range(WIDTH):
            h = state.pulse_history[(x + offset) % WIDTH]
            if h > 0:
                bar_top = base_y - h
                for yp in range(bar_top, base_y + 1):
                    frac = (base_y - yp) / max(1, h)
                    c = Color(
                        min(255, int(agent_color.r * (0.3 + 0.7 * frac))),
                        min(255, int(agent_color.g * (0.3 + 0.7 * frac))),
                        min(255, int(agent_color.b * (0.3 + 0.7 * frac)))
                    )
                    self.set_pixel(x, yp, c)
            else:
                self.set_pixel(x, base_y, agent_color.dim(0.1))

    def render_frame(self, state: AgentState) -> bytes:
        """Render a complete frame and return raw RGB bytes."""
        self.clear()
        self.draw_title_bar(state)
        self.draw_hline(SEP1_Y, state.color.dim(0.2), dotted=True)
        self.draw_activity_icons(state)
        self.draw_hline(SEP2_Y, state.color.dim(0.15), dotted=True)
        self.draw_stats(state)
        self.draw_pulse_line(state)

        raw = []
        for y in range(HEIGHT):
            for x in range(WIDTH):
                c = self.pixels[y][x]
                raw.extend([c.r, c.g, c.b])
        return bytes(raw)


# ── Pixoo Client ─────────────────────────────────────────────

class PixooClient:
    """HTTP client for Divoom Pixoo-64. Uses curl for reliability."""

    def __init__(self, ip: str, port: int = 80):
        self.url = f"http://{ip}:{port}/post"
        self.pic_id = 1
        self._tmp_file = '/tmp/pixoo-frame.json'

    def _post(self, payload: dict, timeout: int = 10) -> bool:
        """Send a POST request to the Pixoo via curl."""
        try:
            data = json.dumps(payload)
            r = subprocess.run(
                ['curl', '-s', '-m', str(timeout), '-X', 'POST', self.url,
                 '-H', 'Content-Type: application/json', '-d', data],
                capture_output=True, text=True, timeout=timeout + 5
            )
            return '"error_code": 0' in r.stdout
        except Exception as e:
            print(f"[pixoo] POST failed: {e}")
            return False

    def _post_file(self, payload: dict, timeout: int = 15) -> bool:
        """Send a large POST request via temp file (for pixel data)."""
        try:
            with open(self._tmp_file, 'w') as f:
                json.dump(payload, f)
            r = subprocess.run(
                ['curl', '-s', '-m', str(timeout), '-X', 'POST', self.url,
                 '-H', 'Content-Type: application/json',
                 '--data-binary', f'@{self._tmp_file}'],
                capture_output=True, text=True, timeout=timeout + 5
            )
            return '"error_code": 0' in r.stdout
        except Exception as e:
            print(f"[pixoo] POST file failed: {e}")
            return False

    def set_channel(self, index: int = 3) -> bool:
        """Switch display to custom/API channel."""
        return self._post({'Command': 'Channel/SetIndex', 'SelectIndex': index})

    def set_brightness(self, brightness: int) -> bool:
        return self._post({'Command': 'Channel/SetBrightness', 'Brightness': brightness})

    def get_pic_id(self) -> int:
        """Query the Pixoo's current PicID counter."""
        try:
            r = subprocess.run(
                ['curl', '-s', '-m', '5', '-X', 'POST', self.url,
                 '-H', 'Content-Type: application/json',
                 '-d', '{"Command":"Draw/GetHttpGifId"}'],
                capture_output=True, text=True, timeout=10
            )
            data = json.loads(r.stdout)
            return data.get('PicId', self.pic_id)
        except Exception:
            return self.pic_id

    def send_frame(self, frame_data: bytes) -> bool:
        """Send a 64x64 RGB frame to the display.
        Queries the device's current PicID and sends with the next sequential ID.
        """
        self.pic_id = self.get_pic_id() + 1
        pixel_b64 = base64.b64encode(frame_data).decode()
        payload = {
            'Command': 'Draw/SendHttpGif',
            'PicNum': 1,
            'PicWidth': WIDTH,
            'PicOffset': 0,
            'PicID': self.pic_id,
            'PicSpeed': 1000,
            'PicData': pixel_b64,
        }
        return self._post_file(payload)

    def initialize(self, brightness: int = 80) -> bool:
        """Switch to custom channel and set brightness. Call once on startup."""
        print(f"[pixoo] Initializing display at {self.url}")
        ok1 = self.set_channel(3)
        ok2 = self.set_brightness(brightness)
        if ok1 and ok2:
            print(f"[pixoo] Display ready (channel 3, brightness {brightness})")
        else:
            print(f"[pixoo] Warning: init partial (channel={ok1}, brightness={ok2})")
        return ok1


# ── Stats Fetcher ────────────────────────────────────────────

def fetch_openclaw_stats() -> Stats:
    """Fetch live stats from openclaw status --json."""
    try:
        result = subprocess.run(
            ['openclaw', 'status', '--json'],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)

        sessions = data.get('sessions', {})
        defaults = sessions.get('defaults', {})
        recent = sessions.get('recent', [])

        model = defaults.get('model', 'unknown')
        ctx_max = defaults.get('contextTokens', 200000)

        # Find main session
        main = None
        for s in recent:
            if s.get('key') == 'agent:main:main':
                main = s
                break
        if not main and recent:
            main = recent[0]

        if main:
            ctx_pct = main.get('percentUsed', 0)
            total_tokens = main.get('totalTokens', 0)
        else:
            ctx_pct = 0
            total_tokens = 0

        # Shorten model name
        model_short = model.replace('claude-', '').replace('anthropic/', '')
        if len(model_short) > 10:
            model_short = model_short[:10]

        return Stats(
            context_percent=ctx_pct,
            context_used_k=total_tokens // 1000,
            context_max_k=ctx_max // 1000,
            total_tokens_k=total_tokens // 1000,
            model_name=model_short,
            version="2026.3.2",
        )
    except Exception as e:
        print(f"[stats] Error: {e}")
        return Stats()


# ── Demo ─────────────────────────────────────────────────────

def demo():
    """Run a visual demo cycling through activity states."""
    import sys
    import random

    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.178.190"
    agent_name = sys.argv[2] if len(sys.argv) > 2 else "RUNE"
    agent_hex = sys.argv[3] if len(sys.argv) > 3 else "#FF3030"
    header_bg_hex = sys.argv[4] if len(sys.argv) > 4 else ""

    print(f"[pixoo] Agent: {agent_name} ({agent_hex})")

    client = PixooClient(ip)
    client.initialize(brightness=80)

    renderer = FrameRenderer()
    stats = fetch_openclaw_stats()
    print(f"[pixoo] Stats: model={stats.model_name}, ctx={stats.context_percent}%, tok={stats.total_tokens_k}K")

    header_bg = Color.from_hex(header_bg_hex) if header_bg_hex else None
    state = AgentState(name=agent_name, color=Color.from_hex(agent_hex), header_bg=header_bg, stats=stats)

    # Seed some pulse history
    for i in range(0, WIDTH, 3):
        if random.random() > 0.3:
            state.pulse_history[i] = random.randint(1, 7)
            if i + 1 < WIDTH:
                state.pulse_history[i + 1] = max(0, state.pulse_history[i] - random.randint(0, 2))

    scenarios = [
        (5,  {'thinking': True},                                      "Thinking"),
        (5,  {'thinking': True, 'tool': True},                        "Think+Tool"),
        (5,  {'tool': True, 'code': True},                            "Tool+Dev"),
        (3,  {},                                                       "Idle"),
        (5,  {'web': True},                                            "Web Search"),
        (5,  {'thinking': True, 'web': True, 'code': True},            "Think+Web+Dev"),
        (3,  {},                                                       "Idle"),
        (5,  {'cron': True},                                           "Cron"),
        (5,  {'thinking': True, 'tool': True, 'web': True},            "Heavy"),
        (5,  {'thinking': True, 'tool': True, 'web': True, 'cron': True, 'code': True}, "ALL"),
        (4,  {'thinking': True},                                       "Thinking"),
        (3,  {},                                                       "Idle"),
    ]

    print("[pixoo] Demo starting...")
    total = 0

    for duration, activities, label in scenarios:
        state.activities = {a: activities.get(a, False) for a in ACTIVITIES}
        print(f"  {label} ({duration}s)")

        if any(activities.values()):
            for _ in range(random.randint(3, 6)):
                idx = random.randint(0, WIDTH - 2)
                state.pulse_history[idx] = random.randint(3, 7)
                state.pulse_history[idx + 1] = random.randint(1, 4)

        for f in range(duration):
            state.pulse_offset += 1
            state.frame_count += 1
            state.decay_pulse()
            frame = renderer.render_frame(state)
            if client.send_frame(frame):
                total += 1
            time.sleep(1)

    print(f"[pixoo] Demo complete! {total} frames sent.")


if __name__ == '__main__':
    demo()
