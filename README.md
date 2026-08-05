# DJI RC Plus → Windows 虚拟手柄 + 触摸板桥接

将 **DJI RC Plus 遥控器**（RM700 / DJI_RC_Plus）通过 USB 连接到 Windows 电脑后，一键变身：

- 🎮 **虚拟 Xbox 360 手柄** —— 摇杆、波轮、十字键、按键全部映射（无需游戏手柄硬件）
- 🖱️ **笔记本式触摸板** —— 单击 / 双击 / 拖动 / 滚动 / 右键 / 移动指针
- ⌨️ **F1-F6 自定义按键** —— 可映射为手柄按钮或键盘按键

> 适用于大疆遥控器（含带屏遥控器如 DJI RC Pro / RC 2 等）通过 USB 调试连接 Windows，实现“用遥控器当游戏手柄和鼠标”的场景。例如在电脑上玩模拟飞行、无人机模拟器，或把遥控器当作客厅遥控器操作电脑。

---

## 目录

- [功能特性](#功能特性)
- [工作原理](#工作原理)
- [环境要求](#环境要求)
- [安装依赖（详细）](#安装依赖详细)
- [使用方法](#使用方法)
- [按键映射](#按键映射)
- [触摸板手势](#触摸板手势)
- [配置文件说明](#配置文件说明)
- [常见问题排查](#常见问题排查)
- [免责声明](#免责声明)

---

## 功能特性

| 模块 | 功能 |
| ---- | ---- |
| 左摇杆 | 手柄左摇杆（Y 轴已反转，符合游戏习惯） |
| 右摇杆 | 手柄右摇杆（Y 轴已反转） |
| 左波轮 | 手柄 **LT** 扳机（线性，归零位 127） |
| 右波轮 | 手柄 **RT** 扳机（线性） |
| 十字键 | 手柄 D-Pad（方向键） |
| 左摇杆下压 (LSB) | 手柄 **A** 键 |
| 左肩键 | 手柄 **LB** 键 |
| 右肩键 | 手柄 **RB** 键 |
| F1 - F6 | 自定义映射：手柄按钮 或 键盘按键（可配置） |
| 触摸屏 | 笔记本式触摸板（详见[触摸板手势](#触摸板手势)） |

---

## 工作原理

```
DJI RC Plus (RM700)
   │ USB 连接 + ADB 调试
   ▼
adb shell getevent -l   ← 实时读取遥控器的输入事件
   ▼
rc_gamepad.py            ← 解析摇杆/波轮/按键/触摸事件
   ├── vgamepad (ViGEmBus) ──► 虚拟 Xbox 360 手柄
   └── ctypes SendInput ─────► 鼠标 / 键盘（零依赖）
```

- 输入节点按**设备名**动态识别（`DJI embedded joystick` / `gpio-keys` / `fts_ts`），节点号变化也不影响。
- 触摸板事件仅在前台应用为指定包名（默认 `com.Touchpad.air`）时生效，防止误触。

---

## 环境要求

| 项目 | 要求 |
| ---- | ---- |
| 操作系统 | **Windows 10 / 11**（64 位） |
| Python | **3.8+**（本机测试使用 3.14） |
| 遥控器 | DJI RC Plus（RM700），已开启 **USB 调试** |
| USB 连接 | 数据线连接电脑，遥控器屏幕弹出授权提示时点击**允许** |
| 手柄支持 | 虚拟手柄需要安装 **ViGEmBus** 驱动 |

---

## 安装依赖（详细）

### 1. 安装 Python

前往 https://www.python.org/downloads/ 下载并安装 Python 3.8 或更高版本。

> **注意**：安装时务必勾选 **"Add Python to PATH"**（把 Python 加入环境变量），否则命令行无法直接运行 `python`。

安装完成后，在命令提示符（`Win + R` → 输入 `cmd` → 回车）中验证：

```bat
python --version
```

正常会输出类似 `Python 3.14.x` 的版本号。

### 2. 安装虚拟手柄驱动 ViGEmBus（必须）

虚拟手柄功能依赖微软开源的 **ViGEmBus** 内核驱动：

1. 前往 https://github.com/nefarius/ViGEmBus/releases/latest
2. 下载 `ViGEmBus_Setup_x64.exe`（64 位系统）
3. **以管理员身份运行**安装，一路下一步即可
4. 安装完成后建议**重启电脑**

> 不安装此驱动，运行脚本时会报 `[错误] 无法加载虚拟手柄`。

### 3. 安装 Python 依赖 vgamepad

`vgamepad` 是控制 ViGEmBus 虚拟手柄的 Python 库。在命令提示符中执行：

```bat
pip install vgamepad
```

国内网络较慢时可使用镜像源：

```bat
pip install vgamepad -i https://pypi.tuna.tsinghua.edu.cn/simple
```

验证安装是否成功：

```bat
python -c "import vgamepad; print('vgamepad OK')"
```

### 4. ADB（Android Debug Bridge）

本项目文件夹内已自带 `adb.exe` 及配套 DLL（来自 Google 官方 platform-tools），**无需单独下载**。

如果删除或需要更新，可从官方地址获取：https://developer.android.com/tools/releases/platform-tools

### 依赖汇总表

| 依赖 | 用途 | 安装方式 |
| ---- | ---- | -------- |
| Python 3.8+ | 运行环境 | python.org 安装包，勾选 Add to PATH |
| ViGEmBus 驱动 | 虚拟 Xbox 手柄内核驱动 | 官网 exe，管理员运行，装完重启 |
| vgamepad | Python 控制虚拟手柄 | `pip install vgamepad` |
| ADB (platform-tools) | 读取遥控器输入事件 | 文件夹已自带（或 Google 官网下载） |
| ctypes（标准库） | 鼠标/键盘模拟 | Python 自带，无需安装 |

---

## 使用方法

1. **遥控器开启 USB 调试**：
   - 进入遥控器「设置 → 关于 → 连续点击版本号」打开开发者选项
   - 在开发者选项里开启「USB 调试」
2. **连接电脑**：用 USB 数据线连接遥控器与电脑，遥控器屏幕弹出授权弹窗时选择「允许」
3. 确认设备被识别（可选）：

   ```bat
   adb devices
   ```
   应显示设备列表，如 `4LFCL2F004BYMA  device`（`device` 表示已授权）
4. **运行脚本**：

   ```bat
   python rc_gamepad.py
   ```

   看到以下输出即成功：

   ```
   [成功] 虚拟手柄驱动已加载！
   [成功] 摇杆节点: event6 (DJI embedded joystick)
   [成功] 触摸板节点: event5 (fts_ts)，模式: relative
   [成功] 开始监听，请操作...
   ```

5. 在游戏 / 系统里把控制器识别为 **"Xbox 360 Controller"** 即可使用；按 `Ctrl + C` 停止脚本。

> 手柄键鼠需要脚本保持运行（占用一个终端窗口），脚本退出后一切恢复正常。

---

## 按键映射

### 默认映射

| 遥控器按键 | 手柄按钮 |
| ---------- | -------- |
| 左摇杆下压 (LSB) | A |
| 左肩键 | LB |
| 右肩键 | RB |
| F1 | A |
| F2 | B |
| F3 | X |
| F4 | Y |
| F5 | LB |
| F6 | RB |

### F1-F6 自定义映射

在 `config.json` 的 `keys` 字段中配置（键名使用 `F1` ~ `F6`）：

```json
"keys": {
  "F1": {"type": "gamepad", "button": "A"},    // 手柄按钮
  "F2": {"type": "gamepad", "button": "X"},
  "F3": {"type": "keyboard", "key": "CTRL"},   // 键盘按键
  "F4": {"type": "keyboard", "key": "F5"},
  "F5": {"type": "keyboard", "key": "TAB"}
}
```

- **gamepad 可用按钮**：`A B X Y`、`LB RB`、`BACK START GUIDE`、`DPAD_UP/DOWN/LEFT/RIGHT`、`L3 R3`（同 `LS RS`）
- **keyboard 可用按键**：字母 `A-Z`、数字 `0-9`、`F1-F12`、`ENTER TAB ESC SPACE BACKSPACE DELETE HOME END PAGEUP PAGEDOWN INSERT CAPSLOCK NUMLOCK`、方向键 `UP/DOWN/LEFT/RIGHT`、修饰键 `SHIFT CTRL ALT WIN`（按下期间持续按住）、符号 `- = [ ] \ ; ' , . / \``

---

## 触摸板手势

触摸板采用**标准笔记本触摸板逻辑**（默认 `relative` 模式，光标跟随手指相对移动）：

| 手势 | 效果 |
| ---- | ---- |
| 单指轻触 | 单击（左键） |
| 快速两次轻触 | 双击 |
| 单指滑动 | 移动鼠标指针 |
| 单指按住 ≥ 500ms 后移动 | 拖动（左键按住拖拽，松手即停） |
| 双指轻触（无移动） | 右键点击 |
| 双指滑动 | 滚动（滚轮） |
| 单击后快速按住（tap-and-hold） | 启动拖动 |

防误触设计：

- 按下稳定期（150ms）内忽略坐标跳变，防止点击瞬间指针乱跳
- 双指滚动发生后 100ms 内锁定右键，避免滚动误触右键
- 单帧坐标跳变超过 200px 的异常帧直接丢弃

> 触摸板**仅在前台运行指定应用时生效**（默认 `com.Touchpad.air`，即遥控器原生「触摸板」App）。在遥控器上打开该 App，即可在电脑上操作。可修改 `config.json` 的 `foreground_pkg` 或关闭 `enable_foreground_check`。

---

## 配置文件说明

配置文件 `config.json` 与脚本同目录，**支持 `//` 行注释和 `/* */` 块注释**（标准 JSON 不允许注释，本脚本已做兼容处理）。修改后重新运行脚本生效。

| 配置项 | 默认值 | 说明 |
| ------ | ------ | ---- |
| `mode` | `"relative"` | 触摸板模式：`relative` 相对滑动 / `absolute` 绝对定位 |
| `touch_width` / `touch_height` | `1200` / `1920` | 触摸屏分辨率（绝对模式映射用） |
| `relative_speed` | `2.5` | 光标灵敏度倍率 |
| `rotation` | `90` | 触摸方向旋转（逆时针 0/90/180/270） |
| `move_threshold` | `10` | 滑动生效阈值（像素），小于此位移视为轻触 |
| `stabilize_ms` | `150` | 按下稳定期，期间忽略坐标跳变 |
| `long_press_ms` | `500` | 长按判定时长（触发拖动） |
| `tap_time_ms` | `200` | 轻触判定最长时长 |
| `double_tap_gap_ms` | `300` | 双击 / 拖拽启动的间隔窗口 |
| `scroll_speed` | `60` | 双指滚动灵敏度（越小越快） |
| `two_finger_right_click` | `true` | 双指轻触是否触发右键 |
| `foreground_pkg` | `"com.Touchpad.air"` | 前台包名白名单 |
| `enable_foreground_check` | `true` | 是否启用前台包检测 |
| `foreground_check_interval` | `3` | 前台包轮询间隔（秒） |
| `keys` | `{}` | F1-F6 自定义映射 |
| `debug` | `false` | 触摸板调试日志开关 |

---

## 常见问题排查

**Q1：提示 `[错误] 无法加载虚拟手柄`**
→ 未安装 ViGEmBus 驱动，或安装后未重启电脑。见[安装依赖](#安装依赖详细)第 2 步。

**Q2：提示 `[错误] 未找到 DJI embedded joystick 节点`**
→ 遥控器未连接 / USB 调试未开启 / 授权弹窗未允许。运行 `adb devices` 确认设备状态，重新插拔并点「允许」。

**Q3：游戏里看不到手柄**
→ 确认 ViGEmBus 驱动已安装；游戏需要支持 Xbox 360 手柄（多数现代游戏支持）；部分游戏需在设置里启用手柄输入。

**Q4：键盘按键映射没反应**
→ 检查 `config.json` 的 `keys` 中 `type` 是否为 `"keyboard"` 且 `key` 名称拼写正确（如 `CTRL`、`F5`）。按键注入依赖目标窗口焦点，请确认窗口在前台。

**Q5：触摸板不动**
→ 确认遥控器前台打开的是 `foreground_pkg` 指定的 App（默认 `com.Touchpad.air`）；或把 `enable_foreground_check` 设为 `false` 全部放开。

**Q6：方向反了 / 灵敏度不合适**
→ 修改 `config.json` 的 `rotation`（触摸方向）、`relative_speed`（灵敏度）、`scroll_speed`（滚动速度）。

**Q7：按 F 键时终端打印 `检测到按键: KEY_Fx` 但没效果**
→ 属正常日志。若映射未生效，确认 `keys` 里的键名是 `F1` 而非 `KEY_F1`。

---

## 免责声明

本项目仅用于学习与个人娱乐用途，不隶属于 DJI（大疆）或 Microsoft。使用本项目造成的任何设备、系统或账号问题，作者不承担责任。

---

## 目录结构

```
platform-tools/
├── rc_gamepad.py        # 主程序（全部逻辑）
├── config.json          # 配置文件（带详细注释）
├── adb.exe              # ADB 工具（官方 platform-tools）
├── AdbWinApi.dll
├── AdbWinUsbApi.dll
└── ...                  # 其他 platform-tools 附属文件
```
