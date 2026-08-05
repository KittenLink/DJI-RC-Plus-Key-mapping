import subprocess
import os
import json
import time
import re
import threading
import ctypes
import vgamepad as vg
import sys

# === 配置区域 ===
# 灵敏度设置
STICK_SCALE = 1.0      # 摇杆灵敏度 (X/Y)
WHEEL_SCALE = 1.0      # 波轮灵敏度 (Z/RZ)，数值越大波轮越灵敏

# === 外部配置文件 (config.json，与脚本同目录) ===
# 触摸板模式: "absolute" = 绝对定位(点哪指哪) / "relative" = 相对滑动(像笔记本触摸板)
DEFAULT_CONFIG = {
    "mode": "relative",
    "touch_width": 1200,
    "touch_height": 1920,
    "relative_speed": 2.5,
    "two_finger_right_click": True,
    "move_threshold": 10,       # 滑动生效所需位移(像素)，滤除轻触抖动
    "stabilize_ms": 150,        # 按下稳定期: 期间持续刷新基准点，忽略坐标跳变
    "long_press_ms": 500,       # 长按判定: 按住超过此时长后移动 = 拖动(按下左键)
    "tap_time_ms": 200,         # 轻触最长时长: 快于此时长+小位移 = 单击
    "double_tap_gap_ms": 300,   # 双击/拖拽启动间隔: 单击后此时间内再次按住 = 拖拽
    "scroll_speed": 60,         # 双指滚动: 多少像素滚一格(120单位)
    "foreground_pkg": "com.Touchpad.air",  # 仅当前台为该应用时启用触摸板
    "enable_foreground_check": True,
    "foreground_check_interval": 3,  # 前台包名轮询间隔(秒)
    "debug": False,             # True 时打印触摸状态调试日志
    "keys": {},                 # F1-F6 自定义按键, 见 config.json 示例
    "rotation": 90
}

# 坐标旋转变换 (角度为逆时针): (x, y) -> (rx, ry)
def rotate(x, y):
    r = CONFIG.get("rotation", 0) % 360
    w = CONFIG["touch_width"]
    h = CONFIG["touch_height"]
    if r == 90:
        return y, w - 1 - x
    elif r == 180:
        return w - 1 - x, h - 1 - y
    elif r == 270:
        return h - 1 - y, x
    return x, y

def strip_json_comments(text):
    # 移除 // 行注释 和 /* */ 块注释 (自动跳过字符串内的内容)
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == '\\':
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            while i < n and text[i] != '\n':
                i += 1
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            i += 2
            while i + 1 < n and not (text[i] == '*' and text[i + 1] == '/'):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return ''.join(out)

def load_config():
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                raw = f.read()
            cfg = json.loads(strip_json_comments(raw))
            cfg = {**DEFAULT_CONFIG, **cfg}
            print(f"[提示] 已加载配置: {cfg_path}")
            return cfg
        except Exception as e:
            print(f"[警告] 配置文件解析失败，使用默认值: {e}")
    else:
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
            print(f"[提示] 已生成默认配置: {cfg_path} (可修改后重新运行)")
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

CONFIG = load_config()

# === Windows 鼠标控制 (ctypes SendInput, 零依赖) ===
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_void_p)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("mi", MOUSEINPUT)]

user32 = ctypes.windll.user32

def mouse_event(flags, dx=0, dy=0, wheel=0):
    mi = MOUSEINPUT(dx, dy, wheel, flags, 0, None)
    inp = INPUT(0, mi)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

# === 键盘模拟 (ctypes SendInput, 零依赖) ===
KEYEVENTF_KEYUP = 0x0002

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_void_p)]

class KEYBD_INPUT_UNION(ctypes.Union):
    # union 需与 MOUSEINPUT 同大小, 否则 64 位下 INPUT 结构尺寸不符导致 SendInput 失败 (0x57)
    _fields_ = [("ki", KEYBDINPUT),
                ("mi", MOUSEINPUT)]

class KEYBD_INPUT_EVENT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),  # 1 = INPUT_KEYBOARD
                ("u", KEYBD_INPUT_UNION)]

def send_key(vk, down):
    flags = 0 if down else KEYEVENTF_KEYUP
    ki = KEYBDINPUT(vk, 0, flags, 0, None)
    inp = KEYBD_INPUT_EVENT(1, KEYBD_INPUT_UNION(ki=ki))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

# 虚拟键码表 (Windows Virtual-Key Codes)
VK_MAP = {chr(ord('A') + i): 0x41 + i for i in range(26)}
VK_MAP.update({chr(ord('0') + i): 0x30 + i for i in range(10)})
VK_MAP.update({f"F{i}": 0x6F + i for i in range(1, 13)})
VK_MAP.update({
    "ENTER": 0x0D, "RETURN": 0x0D, "ESC": 0x1B, "ESCAPE": 0x1B, "TAB": 0x09, "SPACE": 0x20,
    "BACKSPACE": 0x08, "DELETE": 0x2E, "DEL": 0x2E, "HOME": 0x24, "END": 0x23,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22, "INSERT": 0x2D,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    "SHIFT": 0x10, "CTRL": 0x11, "CONTROL": 0x11, "ALT": 0x12, "MENU": 0x12, "WIN": 0x5B,
    "CAPSLOCK": 0x14, "NUMLOCK": 0x90,
    "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA,
    "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "`": 0xC0,
})

def get_vk(name):
    if not name:
        return None
    key = name.upper()
    if key in VK_MAP:
        return VK_MAP[key]
    if len(key) == 1:  # 未收录的单字符按 ASCII
        return ord(key)
    return None

# === F1-F6 自定义按键映射 (config.json: keys) ===
BUTTON_MAP = {
    "A": vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
    "B": vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
    "X": vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
    "Y": vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
    "LB": vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
    "RB": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
    "BACK": vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
    "START": vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
    "DPAD_UP": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
    "DPAD_DOWN": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
    "DPAD_LEFT": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
    "DPAD_RIGHT": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
    "L3": vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
    "R3": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
    "LS": vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
    "RS": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
    "GUIDE": vg.XUSB_BUTTON.XUSB_GAMEPAD_GUIDE,
}

# 未在 config.json 配置时的默认手柄映射
DEFAULT_KEYS = {"F1": "A", "F2": "B", "F3": "X", "F4": "Y", "F5": "LB", "F6": "RB"}
KEY_ACTIONS = CONFIG.get("keys", {})

def get_key_action(name):
    # 事件码是 KEY_F1, 配置键名是 F1, 去掉前缀
    if name.startswith("KEY_F"):
        name = name[4:]
    cfg = KEY_ACTIONS.get(name)
    if cfg is None:
        btn = DEFAULT_KEYS.get(name)
        if btn is None:
            return None
        return {"type": "gamepad", "button": btn}
    return cfg

def press_key_action(action, down):
    t = action.get("type", "gamepad")
    if t == "keyboard":
        vk = get_vk(action.get("key", ""))
        if vk:
            send_key(vk, down)
        return True
    elif t == "gamepad":
        btn = BUTTON_MAP.get(str(action.get("button", "")).upper())
        if btn:
            if down:
                gamepad.press_button(btn)
            else:
                gamepad.release_button(btn)
        return True
    return False

# === 触摸板 (标准笔记本触摸板逻辑) ===
# 状态机:
#   idle      无操作
#   hold      单指按下未定 (移动->move 抬起->轻触判定)
#   move      单指滑动: 移动指针 (不按左键)
#   tap_wait  单击后等待 (此时间内再次按住=拖拽, 再次轻触=双击)
#   tap_hold  第二次按住: 移动即拖动 (按下左键)
#   drag      拖拽中 (左键按住, 移动=拖动)
#   two       双指: 轻触=右键 / 滑动=滚动
touch = {}            # slot -> [tracking_id, x, y]
cur_slot = 0          # 当前 ABS_MT_SLOT
active_fingers = 0    # 有效触点数量
MAX_FRAME_JUMP = 200  # 单帧坐标跳变上限(px)，丢弃按下/抬起瞬间的突变帧
mode = "idle"         # 当前状态
press_pos = None      # 按下起点 (轻触位移判定)
press_time = None     # 按下时刻
finger_pos = None     # 单指最新坐标
last_pos = None       # 移动/拖动基准点
left_down = False     # 左键当前是否按下
last_tap_time = None  # 上次单击时刻 (双击/拖拽启动判定)
two_center = None     # 双指中心
scroll_accum = 0      # 滚动累积量
two_candidate = False # 双指轻触候选: 双指均未移动/滚动时松开 = 右键
two_active = False    # 是否曾进入双指状态
two_press_time = None # 第二指落下时刻 (快速点击时间窗)
right_locked = False  # 右键功能锁定 (滚动发生后)
right_unlock_at = 0   # 解锁时刻 (松开后 100ms)

def is_right_locked():
    # 锁定到期自动解锁
    global right_locked, right_unlock_at
    if right_locked and right_unlock_at and time.monotonic() >= right_unlock_at:
        right_locked = False
    return right_locked

# === 前台包名检测 (触摸板仅在前台为指定应用时启用) ===
touch_enabled = True  # 触摸板功能开关 (由前台包名决定)

def start_foreground_watch():
    def worker():
        global touch_enabled
        while True:
            try:
                out = subprocess.run([ADB_PATH, 'shell', 'dumpsys', 'window'],
                                     capture_output=True, text=True, timeout=10).stdout
                m = re.search(r'm(?:CurrentFocus|FocusedApp)=\w*\{[^}]*?([\w.]+)/', out)
                pkg = m.group(1) if m else None
                touch_enabled = (pkg == CONFIG["foreground_pkg"])
            except Exception:
                pass
            time.sleep(CONFIG["foreground_check_interval"])
    t = threading.Thread(target=worker, daemon=True)
    t.start()

if CONFIG["enable_foreground_check"]:
    start_foreground_watch()
    print(f"[提示] 前台包检测已开启: 仅 {CONFIG['foreground_pkg']} 在前台时启用触摸板")
screen_w = user32.GetSystemMetrics(0)
screen_h = user32.GetSystemMetrics(1)

def release_left():
    global left_down
    if left_down:
        mouse_event(MOUSEEVENTF_LEFTUP)
        left_down = False

def send_left_click():
    mouse_event(MOUSEEVENTF_LEFTDOWN)
    mouse_event(MOUSEEVENTF_LEFTUP)

def rotate_delta(dx, dy):
    # 相对位移按逆时针旋转
    r = CONFIG.get("rotation", 0) % 360
    if r == 90:
        return dy, -dx
    elif r == 180:
        return -dx, -dy
    elif r == 270:
        return -dy, dx
    return dx, dy

def move_cursor_relative(dx, dy):
    dx, dy = rotate_delta(dx, dy)
    mx = int(dx * CONFIG["relative_speed"])
    my = int(dy * CONFIG["relative_speed"])
    if mx or my:
        mouse_event(MOUSEEVENTF_MOVE, mx, my)

def set_cursor_absolute(x, y):
    rx, ry = rotate(x, y)
    r = CONFIG.get("rotation", 0) % 360
    # 旋转后逻辑尺寸: 90/270 时宽高互换
    if r in (90, 270):
        lw, lh = CONFIG["touch_height"], CONFIG["touch_width"]
    else:
        lw, lh = CONFIG["touch_width"], CONFIG["touch_height"]
    sx = int(rx / lw * screen_w)
    sy = int(ry / lh * screen_h)
    sx = max(0, min(screen_w - 1, sx))
    sy = max(0, min(screen_h - 1, sy))
    user32.SetCursorPos(sx, sy)

def compute_center():
    # 所有有效触点的中心 (双指滚动用)
    pts = [s[1:3] for s in touch.values() if s[0] >= 0]
    if not pts:
        return None
    return (sum(p[0] for p in pts) // len(pts), sum(p[1] for p in pts) // len(pts))

def on_touch_move(x, y):
    # 触摸位置更新
    global finger_pos, last_pos, press_pos, mode, two_center, scroll_accum, two_candidate, right_locked
    finger_pos = (x, y)
    if CONFIG["mode"] == "absolute":
        if mode in ("hold", "move", "drag") and active_fingers == 1:
            set_cursor_absolute(x, y)
        return
    if mode == "hold":
        # 未定: 位移超过阈值 -> 移动指针 (立即响应, 不按左键)
        if press_pos is None:
            press_pos = (x, y)
            return
        # 按下稳定期: 持续刷新基准点，忽略按下瞬间的坐标跳变
        if press_time and (time.monotonic() - press_time) < CONFIG["stabilize_ms"] / 1000.0:
            press_pos = (x, y)
            return
        # 长按判定: 按住超过 long_press_ms 后移动 = 拖动 (按下左键)
        # (解决: 单击后停顿再按住拖动时, tap_wait 已超时, 走此路径)
        if press_time and (time.monotonic() - press_time) >= CONFIG["long_press_ms"] / 1000.0:
            dx = x - press_pos[0]
            dy = y - press_pos[1]
            if abs(dx) + abs(dy) > 0:  # 长按后有任何位移即拖动
                mouse_event(MOUSEEVENTF_LEFTDOWN)
                left_down = True
                mode = "drag"
                last_pos = press_pos
                move_cursor_relative(x - last_pos[0], y - last_pos[1])
            return
        dx = x - press_pos[0]
        dy = y - press_pos[1]
        if abs(dx) + abs(dy) < CONFIG["move_threshold"]:
            return  # 轻触抖动
        last_pos = press_pos
        mode = "move"
        move_cursor_relative(x - last_pos[0], y - last_pos[1])
    elif mode == "move":
        # 滑动: 移动指针
        if last_pos is None:
            last_pos = (x, y)
            return
        dx = x - last_pos[0]
        dy = y - last_pos[1]
        last_pos = (x, y)
        if abs(dx) + abs(dy) > MAX_FRAME_JUMP:
            return  # 丢弃跳变帧 (按下/抬起瞬间坐标突变)
        move_cursor_relative(dx, dy)
    elif mode == "tap_hold":
        # 第二次按住: 移动即拖动 (左键已按下, 无延迟立即响应)
        if last_pos is None:
            last_pos = (x, y)
            return
        dx = x - last_pos[0]
        dy = y - last_pos[1]
        last_pos = (x, y)
        if abs(dx) + abs(dy) > MAX_FRAME_JUMP:
            return  # 仅过滤异常跳变帧
        mode = "drag"
        move_cursor_relative(dx, dy)
    elif mode == "drag":
        # 拖拽: 移动 = 拖动
        if last_pos is None:
            last_pos = (x, y)
            return
        dx = x - last_pos[0]
        dy = y - last_pos[1]
        last_pos = (x, y)
        if abs(dx) + abs(dy) > MAX_FRAME_JUMP:
            return
        move_cursor_relative(dx, dy)
    elif mode == "two":
        # 双指滑动: 滚动 (中心位移 -> 滚轮)
        c = compute_center()
        if c:
            if two_center:
                # 双指落下稳定期内: 仅校准基准，不判滚动/不清右键候选
                settled = not two_press_time or (time.monotonic() - two_press_time) >= CONFIG["stabilize_ms"] / 1000.0
                if settled:
                    dx = c[0] - two_center[0]
                    dy = c[1] - two_center[1]
                    # 双指产生位移 = 滚动意图: 取消右键候选并锁定右键
                    if abs(dx) + abs(dy) >= CONFIG["move_threshold"]:
                        two_candidate = False
                        right_locked = True
                    if abs(dx) + abs(dy) <= MAX_FRAME_JUMP:  # 中心跳变忽略
                        rx, ry = rotate_delta(dx, dy)
                        # 手指下滑(ry>0) = 内容向下 = 滚轮负值
                        scroll_accum += ry
                        units = int(scroll_accum / CONFIG["scroll_speed"])
                        if units:
                            mouse_event(MOUSEEVENTF_WHEEL, wheel=-units * 120)
                            scroll_accum -= units * CONFIG["scroll_speed"]
            two_center = c

def debug_log(*args):
    if CONFIG.get("debug", False):
        print("[触摸调试]", *args)

def on_finger_change(rising):
    # rising=True: 手指落下  rising=False: 手指抬起
    global mode, press_pos, press_time, finger_pos, last_pos, left_down, last_tap_time, two_center, scroll_accum, two_candidate, two_active, two_press_time, right_unlock_at
    n = active_fingers
    now = time.monotonic()
    debug_log(f"手指{'落下' if rising else '抬起'} 总数={n} mode={mode} two_active={two_active} candidate={two_candidate} locked={is_right_locked()}")

    # tap_wait 惰性超时: 超过间隔后不再响应双击/拖拽
    if mode == "tap_wait" and last_tap_time and (now - last_tap_time) > CONFIG["double_tap_gap_ms"] / 1000.0:
        mode = "idle"

    if rising:
        if n == 1:
            if mode == "tap_wait":
                # 单击后快速再次按住 = 拖拽启动 (tap-and-hold)
                mouse_event(MOUSEEVENTF_LEFTDOWN)
                left_down = True
                mode = "tap_hold"
                last_pos = None
            else:
                mode = "hold"
            press_pos = None
            finger_pos = None
            press_time = now
        elif n == 2:
            # 第二指落下: 仅首次进入双指时标记候选，松开时才触发右键
            release_left()
            if not two_active:
                # 首次进入双指: 初始化候选与时间窗
                two_active = True
                two_press_time = now
                if mode == "move":
                    two_candidate = False  # 单指滑动中落下第二指: 不视为轻触
                else:
                    two_candidate = True
            # 滚动中手指交替起落: two_active 已为 True, 保留既有候选(不重置)
            two_center = None
            scroll_accum = 0
            mode = "two"
        else:
            # 三指及以上: 释放左键, 双指逻辑继续
            release_left()
            two_candidate = False
            two_center = None
            scroll_accum = 0
            mode = "two"
    else:
        if n == 0:
            if two_active:
                # 双指流程结束: 候选成立(未移动/未滚动)且未锁定才触发右键
                two_active = False
                right_unlock_at = now + 0.1  # 松开后 100ms 解锁右键
                if two_candidate and CONFIG["two_finger_right_click"] and not is_right_locked():
                    debug_log(">> 触发右键")
                    mouse_event(MOUSEEVENTF_RIGHTDOWN)
                    mouse_event(MOUSEEVENTF_RIGHTUP)
                else:
                    debug_log(f">> 未触发右键: candidate={two_candidate} locked={is_right_locked()}")
                two_candidate = False
                two_press_time = None
                mode = "idle"
                press_pos = None
                press_time = None
                finger_pos = None
                last_pos = None
                return
            # 单指流程: 全部抬起
            if mode == "hold":
                # 轻触判定: 小位移 + 短时长 = 单击
                moved = 0
                if press_pos and finger_pos:
                    moved = abs(finger_pos[0] - press_pos[0]) + abs(finger_pos[1] - press_pos[1])
                held = (now - press_time) if press_time else 999
                if moved < CONFIG["move_threshold"] and held < CONFIG["tap_time_ms"] / 1000.0:
                    send_left_click()
                    last_tap_time = now
                    mode = "tap_wait"
                else:
                    mode = "idle"
            elif mode == "tap_hold":
                # 第二次按住后抬起: 若快速抬起(未移动) = 双击
                release_left()
                moved = 0
                if press_pos and finger_pos:
                    moved = abs(finger_pos[0] - press_pos[0]) + abs(finger_pos[1] - press_pos[1])
                if moved < CONFIG["move_threshold"] and press_time and (now - press_time) < CONFIG["double_tap_gap_ms"] / 1000.0:
                    send_left_click()
                    last_tap_time = now
                    mode = "tap_wait"
                else:
                    mode = "idle"
            elif mode == "drag":
                debug_log(">> 拖动结束, 释放左键 (松手即停)")
                release_left()
                mode = "idle"
            else:
                mode = "idle"
            press_pos = None
            press_time = None
            finger_pos = None
            last_pos = None
        elif n == 1:
            # 双指抬起一指: 回到单指 (保留右键候选, 移动会取消)
            release_left()
            mode = "hold"
            press_pos = None
            finger_pos = None
            last_pos = None
            press_time = now
        else:
            # 多指仍有两个以上
            pass

# 自动寻找 ADB
if os.path.exists("adb.exe"):
    ADB_PATH = "adb.exe"
else:
    ADB_PATH = "adb"

# 初始化虚拟手柄
try:
    gamepad = vg.VX360Gamepad()
    print("[成功] 虚拟手柄驱动已加载！")
except Exception as e:
    print(f"[错误] 无法加载虚拟手柄: {e}")
    sys.exit()

print(f"[提示] 使用 ADB: {ADB_PATH}")
print("[提示] 左波轮 -> LT (刹车/瞄准)")
print("[提示] 右波轮 -> RT (油门/射击)")
print("正在连接 RC Plus...")

# 动态识别输入节点 (节点号会因开机顺序变化，按设备名查找最稳妥)
def find_input_nodes():
    nodes = {}
    try:
        out = subprocess.run([ADB_PATH, 'shell', 'getevent', '-pl'],
                             capture_output=True, text=True, timeout=10).stdout
        current = None
        for line in out.splitlines():
            if line.startswith("add device"):
                current = line.split("/dev/input/")[-1].split(":")[0]
            elif "name:" in line and current and '"' in line:
                name = line.split('"')[1]
                nodes[name] = current
    except Exception as e:
        print(f"[警告] 无法识别节点: {e}")
    return nodes

nodes = find_input_nodes()
joy_node = nodes.get("DJI embedded joystick")
key_node = nodes.get("gpio-keys")
if not joy_node:
    print("\n[错误] 未找到 DJI embedded joystick 节点，请确认遥控器已连接并开启 USB 调试！")
    sys.exit()
print(f"[成功] 摇杆节点: {joy_node} ({'DJI embedded joystick'})")
print(f"[提示] 按键节点: {key_node or '未找到 gpio-keys'}")

touch_node = nodes.get("fts_ts")
if touch_node:
    print(f"[成功] 触摸板节点: {touch_node} (fts_ts)，模式: {CONFIG['mode']}")
else:
    print("[提示] 未找到 fts_ts 触摸节点，触摸板功能禁用")

# 启动监听
cmd = [ADB_PATH, 'shell', 'getevent', '-l']
try:
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
except FileNotFoundError:
    print("\n[错误] 找不到 adb.exe，请把脚本放到 platform-tools 文件夹里！")
    sys.exit()

# 状态存储
state = {
    'LX': 0, 'LY': 0,
    'RX': 0, 'RY': 0,
    'LT': 127, 'RT': 127 # 波轮状态 (初始为归零值 0x7f)
}
hat_x = 0  # 十字键横向: -1左 0中 1右
hat_y = 0  # 十字键纵向: -1上 0中 1下

def hex_to_int(hex_str):
    try:
        val = int(hex_str, 16)
        if val > 0x7FFFFFFF: val -= 0x100000000
        return val
    except: return 0

def update_gamepad():
    # 1. 处理摇杆 (限制在 -32768 到 32767)
    lx = int(max(-32768, min(32767, state['LX'] * STICK_SCALE)))
    ly = int(max(-32768, min(32767, -state['LY'] * STICK_SCALE))) # Y轴反转
    rx = int(max(-32768, min(32767, state['RX'] * STICK_SCALE)))
    ry = int(max(-32768, min(32767, -state['RY'] * STICK_SCALE))) # Y轴反转
    
    gamepad.left_joystick(x_value=lx, y_value=ly)
    gamepad.right_joystick(x_value=rx, y_value=ry)

    # 1.5 十字键 (HAT) -> D-Pad
    set_dpad(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,  hat_x == -1)
    set_dpad(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, hat_x == 1)
    set_dpad(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,    hat_y == -1)
    set_dpad(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,  hat_y == 1)

    # 2. 处理波轮 -> 线性扳机 (LT/RT)
    # 波轮中心 (归零位) 是 0x7f (127)，向上/向下拨动偏离中心
    # 取偏离量 |val - 127|，乘以 2 把 0-127 行程放大到 0-254
    
    # 左波轮控制 LT
    lt_val = int(abs(state['LT'] - 127) * 2 * WHEEL_SCALE)
    lt_val = max(0, min(255, lt_val))
    
    # 右波轮控制 RT
    rt_val = int(abs(state['RT'] - 127) * 2 * WHEEL_SCALE)
    rt_val = max(0, min(255, rt_val))

    gamepad.left_trigger(value=lt_val)
    gamepad.right_trigger(value=rt_val)

    gamepad.update()

def set_dpad(btn, on):
    # 只在状态变化时按下/释放，避免重复发送相同报告
    key = btn.value
    if on and key not in dpad_pressed:
        gamepad.press_button(btn)
        dpad_pressed.add(key)
    elif not on and key in dpad_pressed:
        gamepad.release_button(btn)
        dpad_pressed.discard(key)

dpad_pressed = set()

print("[成功] 开始监听，请操作...")

try:
    for line in process.stdout:
        line = line.strip()
        if not line: continue
        parts = line.split()
        if len(parts) < 4: continue

        device = parts[0].replace(":", "")
        ev_type = parts[1]
        code = parts[2]
        value_hex = parts[3]

        # === 处理摇杆与波轮 (joystick 节点) ===
        if joy_node in device and ev_type == "EV_ABS":
            val = hex_to_int(value_hex)
            
            # 摇杆
            if code == "ABS_X": state['LX'] = val
            elif code == "ABS_Y": state['LY'] = val
            elif code == "ABS_RX": state['RX'] = val
            elif code == "ABS_RY": state['RY'] = val
            
            # 波轮 (这里就是刚才缺少的代码)
            elif code == "ABS_Z": state['LT'] = val  # 左波轮
            elif code == "ABS_RZ": state['RT'] = val # 右波轮

            # 十字键 (HAT): -1 上/左, 1 下/右
            elif code == "ABS_HAT0X": hat_x = val  # 左(-1) / 右(1)
            elif code == "ABS_HAT0Y": hat_y = val  # 上(-1) / 下(1)

            update_gamepad()

        # === 处理 joystick 节点上的按键 ===
        elif joy_node in device and ev_type == "EV_KEY":
            is_down = (value_hex != "00000000" and value_hex != "UP")

            # 左摇杆下压 (LSB) -> A 键
            if code == "BTN_THUMBL":
                if is_down: gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
                else:       gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
                gamepad.update()
                if is_down: print(f"检测到按键: {code}")

            # 左肩键 -> LB
            elif code == "BTN_TL":
                if is_down: gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
                else:       gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
                gamepad.update()
                if is_down: print(f"检测到按键: {code}")

            # 右肩键 -> RB
            elif code == "BTN_TR":
                if is_down: gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
                else:       gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
                gamepad.update()
                if is_down: print(f"检测到按键: {code}")

        # === 处理触摸板 (fts_ts 节点) ===
        elif touch_node and touch_node in device:
            if CONFIG["enable_foreground_check"] and not touch_enabled:
                # 前台非目标应用: 关闭触摸板, 并重置残留状态
                if mode != "idle" or left_down:
                    release_left()
                    mode = "idle"
                    press_pos = None
                    press_time = None
                    finger_pos = None
                    last_pos = None
                    two_center = None
                    two_active = False
                    two_candidate = False
                    two_press_time = None
                    scroll_accum = 0
                continue
            if ev_type == "EV_ABS":
                val = hex_to_int(value_hex)
                if code == "ABS_MT_SLOT":
                    cur_slot = val
                elif code == "ABS_MT_TRACKING_ID":
                    slot = touch.setdefault(cur_slot, [-1, 0, 0])
                    was_active = slot[0] >= 0
                    slot[0] = val
                    if was_active and val < 0:
                        active_fingers -= 1
                        on_finger_change(False)
                    elif not was_active and val >= 0:
                        active_fingers += 1
                        on_finger_change(True)
                    if val < 0:
                        slot[1], slot[2] = 0, 0
                elif code == "ABS_MT_POSITION_X":
                    slot = touch.setdefault(cur_slot, [-1, 0, 0])
                    if slot[0] >= 0:  # 忽略已抬起触点的坐标
                        slot[1] = val
                        on_touch_move(slot[1], slot[2])
                elif code == "ABS_MT_POSITION_Y":
                    slot = touch.setdefault(cur_slot, [-1, 0, 0])
                    if slot[0] >= 0:  # 忽略已抬起触点的坐标
                        slot[2] = val
                        on_touch_move(slot[1], slot[2])

        # === 处理按键 (gpio-keys 节点, F1-F6 自定义映射) ===
        elif key_node and key_node in device:
            is_down = (value_hex != "00000000" and value_hex != "UP")

            # 自定义映射 (config.json: keys), 未配置时用默认手柄映射
            action = get_key_action(code)
            if action:
                press_key_action(action, is_down)
                if is_down:
                    print(f"检测到按键: {code}")
                gamepad.update()

except KeyboardInterrupt:
    print("\n已停止")
    process.terminate()
