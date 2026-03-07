import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pixoo_display import *
import base64, json, time, random, subprocess, signal

running = True
def stop(sig, frame):
    global running
    running = False
    print("[demo] Stopping...")
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

ACTIVITY_CONFIG['thinking']['color'] = Color(0, 255, 255)
ACTIVITY_CONFIG['tool']['color'] = Color(255, 255, 50)
ACTIVITY_CONFIG['web']['color'] = Color(50, 255, 120)
ACTIVITY_CONFIG['cron']['color'] = Color(255, 50, 255)
ACTIVITY_CONFIG['code']['color'] = Color(255, 180, 0)
ACTIVITY_CONFIG['code']['label'] = 'DEV'

stats = Stats(context_percent=72, context_used_k=144, context_max_k=200,
              total_tokens_k=130, model_name='opus-4-6', version='2026.3.2')

state = AgentState(name='RUNE', color=Color(255, 50, 50), stats=stats)

class BrightRenderer(FrameRenderer):
    def draw_activity_icons(self, state):
        num = len(ACTIVITIES)
        total_w = num * ICON_H + (num - 1) * 4
        sx = (WIDTH - total_w) // 2
        for i, activity in enumerate(ACTIVITIES):
            cfg = ACTIVITY_CONFIG[activity]
            is_active = state.activities[activity]
            color = cfg['color'] if is_active else cfg['color'].dim(0.15)
            ix = sx + i * (ICON_H + 4)
            self.draw_icon(cfg['icon'], ix, ICON_Y, color)
            if is_active:
                glow = cfg['color'].dim(0.3)
                for dx in [-1, ICON_H]:
                    for dy in range(ICON_H):
                        self.set_pixel(ix + dx, ICON_Y + dy, glow)
                for dy in [-1, ICON_H]:
                    for dx in range(ICON_H):
                        self.set_pixel(ix + dx, ICON_Y + dy, glow)
            label = cfg['label']
            label_w = len(label) * 4 - 1
            lx = ix + (ICON_H - label_w) // 2
            lc = cfg['color'] if is_active else cfg['color'].dim(0.3)
            self.draw_text_3x5(label, lx, LABEL_Y, lc)

    def draw_stats(self, state):
        s = state.stats
        y = STATS_Y
        bar_x, bar_w = 15, 34
        self.draw_text_3x5('CTX', 1, y, Color(140, 140, 140))
        self.draw_rect(bar_x, y, bar_x + bar_w - 1, y + BAR_HEIGHT - 1, Color(50, 50, 50))
        fill_w = max(1, int(bar_w * s.context_percent / 100))
        fc = bar_color_for_percent(s.context_percent)
        self.draw_rect(bar_x, y, bar_x + fill_w - 1, y + BAR_HEIGHT - 1, fc)
        self.draw_text_3x5(f'{s.context_percent}%', 51, y, fc)
        y += BAR_HEIGHT + BAR_GAP
        tok_k = s.total_tokens_k
        tok_pct = min(100, int(tok_k / max(1, s.context_max_k) * 100))
        self.draw_text_3x5('TOK', 1, y, Color(140, 140, 140))
        self.draw_rect(bar_x, y, bar_x + bar_w - 1, y + BAR_HEIGHT - 1, Color(50, 50, 50))
        if tok_pct > 0:
            tf = max(1, int(bar_w * tok_pct / 100))
            self.draw_rect(bar_x, y, bar_x + tf - 1, y + BAR_HEIGHT - 1, Color(80, 160, 255))
        self.draw_text_3x5(f'{tok_k}K', 51, y, Color(80, 160, 255))
        y += BAR_HEIGHT + BAR_GAP
        self.draw_text_3x5('LLM', 1, y, Color(140, 140, 140))
        self.draw_text_3x5(s.model_name[:10], 15, y, Color(0, 200, 200))
        y += 6
        self.draw_text_3x5('VER', 1, y, Color(140, 140, 140))
        self.draw_text_3x5(s.version, 15, y, Color(200, 200, 200))

    def draw_pulse_line(self, state):
        agent_color = state.color
        base_y = PULSE_Y
        history = getattr(state, '_pulse_history', None)
        if history is None:
            history = [0] * WIDTH
            state._pulse_history = history
        offset = state.pulse_offset
        for x in range(WIDTH):
            h = history[(x + offset) % WIDTH]
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

renderer = BrightRenderer()
pulse_history = [0] * WIDTH
state._pulse_history = pulse_history

def send_frame(state, pic_id):
    frame = renderer.render_frame(state)
    p = base64.b64encode(frame).decode()
    payload = json.dumps({'Command':'Draw/SendHttpGif','PicNum':1,'PicWidth':64,
                          'PicOffset':0,'PicID':pic_id % 1000,'PicSpeed':1000,'PicData':p})
    with open('/tmp/pixoo-demo.json', 'w') as f:
        f.write(payload)
    r = subprocess.run(['curl', '-s', '-m', '10', '-X', 'POST', 'http://192.168.178.190:80/post',
                       '-H', 'Content-Type: application/json', '--data-binary', '@/tmp/pixoo-demo.json'],
                      capture_output=True, text=True)
    return '"error_code": 0' in r.stdout

scenarios = [
    (8,  {'thinking': True},                                      "Thinking"),
    (6,  {'thinking': True, 'tool': True},                        "Think+Tool"),
    (5,  {'tool': True, 'code': True},                            "Tool+Dev"),
    (4,  {},                                                       "Idle"),
    (6,  {'web': True},                                            "Web Search"),
    (5,  {'thinking': True, 'web': True, 'code': True},            "Think+Web+Dev"),
    (4,  {},                                                       "Idle"),
    (6,  {'cron': True},                                           "Cron"),
    (4,  {'thinking': True},                                       "Thinking"),
    (6,  {'thinking': True, 'tool': True, 'web': True},            "Heavy"),
    (5,  {'thinking': True, 'tool': True, 'web': True, 'cron': True, 'code': True}, "ALL"),
    (4,  {},                                                       "Idle"),
    (6,  {'tool': True},                                           "Tool"),
    (5,  {'code': True},                                           "Dev"),
    (4,  {},                                                       "Idle"),
]

print("[demo] Running until stopped (Ctrl+C / kill)...", flush=True)
pic = 300
total = 0
cycle = 0

while running:
    cycle += 1
    print(f"[demo] Cycle {cycle}", flush=True)
    for duration, activities, label in scenarios:
        if not running:
            break
        state.activities = {a: activities.get(a, False) for a in ACTIVITIES}
        if any(activities.values()):
            for _ in range(random.randint(3, 6)):
                idx = random.randint(0, WIDTH - 2)
                pulse_history[idx] = random.randint(3, 7)
                pulse_history[idx + 1] = random.randint(1, 4)
        for f in range(duration):
            if not running:
                break
            state.pulse_offset += 1
            for i in range(WIDTH):
                if pulse_history[i] > 0 and random.random() > 0.7:
                    pulse_history[i] = max(0, pulse_history[i] - 1)
            pic += 1
            ok = send_frame(state, pic)
            total += 1 if ok else 0
            if total % 20 == 0:
                print(f"  [{label}] frame {total}", flush=True)
            time.sleep(1)

print(f"[demo] Stopped. {total} frames over {cycle} cycles.", flush=True)
