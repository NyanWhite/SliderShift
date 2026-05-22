import json
import os
import time
import threading
import sys
import re
import subprocess
from pynput import keyboard
from ppadb.client import Client as AdbClient

# ==================== 全局配置参数 ====================
# ADB 点击间隔（秒），越小点击越快，但可能被系统限频
CLICK_INTERVAL = 0.008

# 长按检测延迟（秒）
LONG_PRESS_DELAY = 0.3

# 长按触发间隔（秒）
LONG_PRESS_INTERVAL = 0.05

# 屏幕边缘留白（像素），设为0则不留白
SCREEN_MARGIN = 0

# ADB 命令超时（秒）
ADB_TIMEOUT = 10

# 分辨率获取重试间隔（秒）
RESOLUTION_RETRY_DELAY = 2

# 配对成功后等待时间（秒）
PAIR_WAIT_TIME = 1

# 连接成功后等待时间（秒）
CONNECT_WAIT_TIME = 1
# ====================================================

# 配置文件
CONFIG_FILE = "config.json"

# 全局变量
screen_width = 0
screen_height = 0
device = None
stop_clicking = False
clicking_active = False

# 校准变量
vertical_offset = 0
horizontal_offset = 0

# 原始左下角和右下角坐标
original_bottom_left = (0, 0)
original_bottom_right = (0, 0)

# 当前校准后的坐标
current_bottom_left = (0, 0)
current_bottom_right = (0, 0)

# 长按检测变量
key_press_times = {}


# ==================== ADB 相关函数 ====================
def get_adb_path():
    """获取 adb 可执行文件路径，优先使用当前目录下的 adb.exe"""
    current_dir_adb = os.path.join(os.path.dirname(sys.argv[0]), "adb.exe")
    if os.path.exists(current_dir_adb):
        return current_dir_adb
    cwd_adb = os.path.join(os.getcwd(), "adb.exe")
    if os.path.exists(cwd_adb):
        return cwd_adb
    return "adb"


def run_adb_command(args, timeout=ADB_TIMEOUT):
    """执行 adb 命令"""
    adb_path = get_adb_path()
    try:
        result = subprocess.run(
            [adb_path] + args,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout
        )
        return result
    except subprocess.TimeoutExpired:
        print(f"ADB 命令超时: {' '.join(args)}")
        return None
    except FileNotFoundError:
        print(f"未找到 adb 命令: {adb_path}")
        return None


def get_screen_size():
    """获取屏幕分辨率"""
    global screen_width, screen_height
    
    print("正在获取屏幕分辨率...")
    while True:
        try:
            result = device.shell("wm size")
            if result:
                match = re.search(r'(\d+)x(\d+)', result)
                if match:
                    screen_width = int(match.group(1))
                    screen_height = int(match.group(2))
                    print(f"物理分辨率: {screen_width} x {screen_height}")
            
            rotation_result = device.shell("dumpsys input | grep 'SurfaceOrientation'")
            if not rotation_result:
                rotation_result = device.shell("settings get system user_rotation")
            
            rotation = 0
            if rotation_result:
                rot_match = re.search(r'(\d+)', rotation_result)
                if rot_match:
                    rotation = int(rot_match.group(1))
            
            is_landscape = (rotation == 1 or rotation == 3)
            
            if is_landscape:
                if screen_width < screen_height:
                    screen_width, screen_height = screen_height, screen_width
                print(f"✓ 横屏模式 (旋转角度: {rotation * 90}°)")
                print(f"  实际使用分辨率: {screen_width} x {screen_height}\n")
            else:
                print(f"⚠️  提示: 当前为竖屏模式 (旋转角度: {rotation * 90}°)，建议切换到横屏以获得最佳体验")
                print(f"  物理分辨率: {screen_width} x {screen_height}\n")
            
            if screen_width > screen_height:
                print(f"最终使用分辨率: {screen_width} x {screen_height} (横屏)")
            else:
                print(f"最终使用分辨率: {screen_width} x {screen_height} (竖屏)")
            return
            
        except Exception as e:
            print(f"获取分辨率出错: {e}，{RESOLUTION_RETRY_DELAY}秒后重试...")
            time.sleep(RESOLUTION_RETRY_DELAY)


def init_coordinates():
    """初始化原始坐标（左下角和右下角）"""
    global original_bottom_left, original_bottom_right
    
    if screen_width == 0 or screen_height == 0:
        print("错误：屏幕分辨率未获取")
        return False
    
    margin_x = SCREEN_MARGIN
    margin_y = SCREEN_MARGIN
    
    original_bottom_left = (margin_x, screen_height - margin_y)
    original_bottom_right = (screen_width - margin_x, screen_height - margin_y)
    
    print(f"原始左下角: {original_bottom_left}")
    print(f"原始右下角: {original_bottom_right}")
    return True


def update_current_coordinates():
    """根据偏移量更新当前坐标"""
    global current_bottom_left, current_bottom_right, vertical_offset, horizontal_offset
    
    new_left_x = original_bottom_left[0] + horizontal_offset
    new_right_x = original_bottom_right[0] - horizontal_offset
    
    new_left_x = max(0, min(screen_width, new_left_x))
    new_right_x = max(0, min(screen_width, new_right_x))
    
    new_y = original_bottom_left[1] - vertical_offset
    new_y = max(0, min(screen_height, new_y))
    
    current_bottom_left = (int(new_left_x), int(new_y))
    current_bottom_right = (int(new_right_x), int(new_y))


def clicking_loop():
    """快速点击循环"""
    global stop_clicking, clicking_active
    
    clicking_active = True
    print(f"点击循环已启动 (间隔 {CLICK_INTERVAL * 1000:.1f} 毫秒)...")
    
    while not stop_clicking:
        try:
            if device:
                device.input_tap(current_bottom_left[0], current_bottom_left[1])
                device.input_tap(current_bottom_right[0], current_bottom_right[1])
                time.sleep(CLICK_INTERVAL)
        except Exception as e:
            print(f"点击错误: {e}")
            time.sleep(0.1)
    
    clicking_active = False
    print("点击循环已停止")


def get_connection_address():
    """获取连接地址"""
    print("\n" + "=" * 50)
    print("步骤2: 连接设备")
    print("请查看手机无线调试页面中的「连接端口」")
    print("注意：连接端口通常与配对端口不同！")
    print("=" * 50)
    
    time.sleep(0.5)
    sys.stdout.flush()
    sys.stdin.flush()
    
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()
    except:
        pass
    
    result = input("请输入连接地址: ").strip()
    return result


def adb_pair(pair_ip, pair_code):
    """独立的 ADB 配对函数"""
    adb_path = get_adb_path()
    
    try:
        proc = subprocess.Popen(
            [adb_path, "pair", pair_ip],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        stdout, stderr = proc.communicate(input=pair_code + "\n", timeout=ADB_TIMEOUT)
        
        if proc.returncode == 0 and ("Successfully" in stdout or "successful" in stdout.lower() or "paired" in stdout.lower()):
            print("✓ 配对成功！")
            return True
        else:
            print(f"配对失败: {stdout[:200] if stdout else '无输出'}")
            return False
            
    except subprocess.TimeoutExpired:
        proc.kill()
        print("配对超时")
        return False
    except Exception as e:
        print(f"配对出错: {e}")
        return False


def connect_adb_pairing():
    """使用配对码方式连接无线 ADB"""
    
    while True:
        print("\n=== 无线 ADB 连接 ===")
        print("请选择连接方式:")
        print("  1. 输入配对码 (传统方式)")
        print("  2. 直接输入已连接的设备地址")
        print("  3. 退出")
        
        choice = input("请选择 (1/2/3): ").strip()
        
        if choice == "3":
            return False, None, None
        elif choice == "1":
            print("\n请确保：")
            print("  1. 手机已开启开发者选项中的「无线调试」")
            print("  2. 选择「使用配对码配对设备」")
            print()
            
            pair_ip = input("请输入手机的 IP 地址和配对端口 (例如 192.168.1.100:45678): ").strip()
            if not pair_ip:
                print("IP 地址不能为空")
                continue
            
            pair_code = input("请输入 6 位配对码: ").strip()
            if not pair_code or len(pair_code) != 6:
                print("配对码应为 6 位数字")
                continue
            
            if not adb_pair(pair_ip, pair_code):
                retry = input("是否重试？(y/n): ").strip().lower()
                if retry != 'y':
                    continue
            
            print("\n" + "=" * 50)
            print("✓ 配对成功！")
            print("请查看手机无线调试页面中的「连接端口」")
            print("注意：连接端口通常与配对端口不同！")
            print("例如：192.168.1.100:43267")
            print("=" * 50)
            
            connect_ip_port = input("请输入连接地址 (必须包含端口号): ").strip()
            
            if not connect_ip_port:
                print("连接地址不能为空")
                continue
            
            if ":" not in connect_ip_port:
                print("错误：连接地址必须包含端口号，例如 192.168.137.127:43267")
                continue
            
            print(f"正在连接 {connect_ip_port} ...")
            result = run_adb_command(["connect", connect_ip_port])
            
            if result and result.stdout and "connected" in result.stdout.lower():
                print(f"✓ 设备连接成功: {connect_ip_port}")
                adb = AdbClient(host="127.0.0.1", port=5037)
                time.sleep(1)
                devices = adb.devices()
                for dev in devices:
                    if connect_ip_port in dev.serial:
                        return True, adb, dev
                return True, adb, connect_ip_port
            else:
                error_msg = result.stdout if result and result.stdout else "未知错误"
                print(f"连接失败: {error_msg}")
                retry = input("是否重新连接？(y/n): ").strip().lower()
                if retry != 'y':
                    continue
                
        elif choice == "2":
            print("\n直接连接模式 (跳过配对)")
            print("注意：需要输入完整的连接地址，包含端口号")
            print("例如：192.168.137.127:43267")
            
            connect_ip_port = input("请输入连接地址: ").strip()
            if not connect_ip_port:
                print("连接地址不能为空")
                continue
            
            if ":" not in connect_ip_port:
                print("错误：连接地址必须包含端口号，例如 192.168.137.127:43267")
                continue
            
            print(f"正在连接 {connect_ip_port} ...")
            result = run_adb_command(["connect", connect_ip_port])
            
            if result and result.stdout and "connected" in result.stdout.lower():
                print(f"✓ 设备连接成功: {connect_ip_port}")
                adb = AdbClient(host="127.0.0.1", port=5037)
                time.sleep(1)
                devices = adb.devices()
                for dev in devices:
                    if connect_ip_port in dev.serial:
                        return True, adb, dev
                return True, adb, connect_ip_port
            else:
                error_msg = result.stdout if result and result.stdout else "未知错误"
                print(f"连接失败: {error_msg}")
                devices_result = run_adb_command(["devices"])
                if devices_result and devices_result.stdout:
                    lines = devices_result.stdout.strip().split('\n')[1:]
                    for line in lines:
                        if line.strip() and "device" in line:
                            serial = line.split()[0]
                            if ":" in serial:
                                print(f"发现已连接的设备: {serial}")
                                adb = AdbClient(host="127.0.0.1", port=5037)
                                devices = adb.devices()
                                for dev in devices:
                                    if dev.serial == serial:
                                        return True, adb, dev
                                return True, adb, serial
                retry = input("是否重试？(y/n): ").strip().lower()
                if retry != 'y':
                    continue
        else:
            print("无效选择")


def connect_adb():
    """连接 ADB 设备"""
    global device
    
    print("\n正在连接 ADB 设备...")
    
    run_adb_command(["start-server"])
    
    result = run_adb_command(["devices"])
    known_devices = []
    wireless_devices = []
    
    if result and result.stdout:
        lines = result.stdout.strip().split('\n')[1:]
        for line in lines:
            if line.strip() and "device" in line:
                serial = line.split()[0]
                known_devices.append(serial)
                if ":" in serial:
                    wireless_devices.append(serial)
    
    adb = AdbClient(host="127.0.0.1", port=5037)
    all_devices = adb.devices()
    
    usb_devices = []
    for d in all_devices:
        serial = d.serial
        if ":" not in serial and not serial.startswith("adb-"):
            usb_devices.append(d)
    
    if usb_devices:
        device = usb_devices[0]
        print(f"✓ 发现 USB 设备，自动连接: {device.serial}")
        return True
    
    if wireless_devices:
        print(f"发现已配对的无线设备: {wireless_devices}")
        for serial in wireless_devices:
            print(f"尝试自动连接 {serial} ...")
            reconnect_result = run_adb_command(["connect", serial])
            if reconnect_result and "connected" in reconnect_result.stdout.lower():
                print(f"✓ 已自动连接到无线设备: {serial}")
                all_devices = adb.devices()
                for dev in all_devices:
                    if dev.serial == serial:
                        device = dev
                        return True
                device = serial
                return True
            else:
                print(f"连接 {serial} 失败")
    
    print("\n未找到已连接的设备")
    result_tuple = connect_adb_pairing()
    
    if result_tuple is None:
        print("连接已取消")
        return False
    elif len(result_tuple) == 3:
        success, adb_obj, dev = result_tuple
        if success:
            adb = adb_obj
            device = dev
            return True
        else:
            return False
    else:
        print("连接失败")
        return False


# ==================== 配置管理相关函数 ====================
class KeyConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self.config_file = CONFIG_FILE
        self.config = {
            "active_mode": None,
            "32key": {
                "mode": 32,
                "keys": {},
                "limit": False,
                "completed": False
            },
            "16key": {
                "mode": 16,
                "keys": {},
                "limit": False,
                "completed": False
            },
            "air": {
                "mode": "air",
                "keys": {},
                "limit": False,
                "completed": False
            },
            "calibration": {
                "keyboard_left": [0, 0],
                "keyboard_right": [0, 0]
            }
        }
        self.config_modified = False
    
    def load_config(self):
        """加载配置文件"""
        if not os.path.exists(self.config_file):
            return False
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
            
            for mode in ["32key", "16key", "air"]:
                if mode in saved_config:
                    if mode == "32key":
                        keys = saved_config[mode].get("keys", {})
                        saved_config[mode]["completed"] = len(keys) == 32
                    elif mode == "16key":
                        keys = saved_config[mode].get("keys", {})
                        saved_config[mode]["completed"] = len(keys) == 16
                    else:
                        keys = saved_config[mode].get("keys", {})
                        saved_config[mode]["completed"] = len(keys) >= 1
                else:
                    saved_config[mode] = self.config[mode].copy()
                    saved_config[mode]["completed"] = False
            
            if "calibration" not in saved_config:
                saved_config["calibration"] = self.config["calibration"].copy()
            
            if "active_mode" not in saved_config:
                saved_config["active_mode"] = None
            
            self.config = saved_config
            return True
            
        except Exception as e:
            print(f"配置文件读取错误: {e}")
            return False
    
    def save_config(self):
        """保存配置"""
        if self.config_modified:
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                print(f"\n✓ 配置已保存到 {self.config_file}")
                self.config_modified = False
                return True
            except Exception as e:
                print(f"\n✗ 保存失败: {e}")
                return False
        return True
    
    def save_calibration(self, left, right):
        """保存校准数据到配置"""
        self.config["calibration"] = {
            "keyboard_left": list(left),
            "keyboard_right": list(right)
        }
        self.config_modified = True
        self.save_config()
    
    def show_status(self):
        """显示当前配置状态"""
        print("\n" + "=" * 50)
        print("      当前配置状态")
        print("=" * 50)
        
        for mode, name in [("32key", "32key模式"), ("16key", "16key模式"), ("air", "Air模式")]:
            if self.config[mode]["completed"]:
                key_count = len(self.config[mode]["keys"])
                if mode == "32key":
                    print(f"✓ {name}: 已完成 ({key_count}/32个按键)")
                    print(f"  - 缩限模式: {'开启' if self.config[mode]['limit'] else '关闭'}")
                elif mode == "16key":
                    print(f"✓ {name}: 已完成 ({key_count}/16个按键)")
                    print(f"  - 缩限模式: {'开启' if self.config[mode]['limit'] else '关闭'}")
                else:
                    print(f"✓ {name}: 已完成 ({key_count}个按键)")
            else:
                print(f"✗ {name}: 未完成")
        
        cal = self.config["calibration"]
        if cal["keyboard_left"] != [0, 0] or cal["keyboard_right"] != [0, 0]:
            print(f"\n✓ 校准数据: 已配置")
            print(f"  左下角: {cal['keyboard_left']}")
            print(f"  右下角: {cal['keyboard_right']}")
        else:
            print(f"\n✗ 校准数据: 未配置")
        
        if self.config["active_mode"]:
            print(f"\n当前激活模式: {self.config['active_mode']}")
        else:
            print(f"\n当前激活模式: 未选择")
        
        print("=" * 50)
    
    def is_valid_key(self, key):
        """判断是否为需要记录的按键"""
        blocked_keys = [
            keyboard.Key.f1, keyboard.Key.f2, keyboard.Key.f3, keyboard.Key.f4,
            keyboard.Key.f5, keyboard.Key.f6, keyboard.Key.f7, keyboard.Key.f8,
            keyboard.Key.f9, keyboard.Key.f10, keyboard.Key.f11, keyboard.Key.f12,
            keyboard.Key.esc, keyboard.Key.caps_lock, keyboard.Key.num_lock,
            keyboard.Key.scroll_lock, keyboard.Key.print_screen, keyboard.Key.pause,
            keyboard.Key.insert, keyboard.Key.home, keyboard.Key.page_up,
            keyboard.Key.page_down, keyboard.Key.end, keyboard.Key.delete,
            keyboard.Key.cmd, keyboard.Key.shift, keyboard.Key.ctrl, keyboard.Key.alt,
            keyboard.Key.shift_l, keyboard.Key.shift_r, keyboard.Key.ctrl_l,
            keyboard.Key.ctrl_r, keyboard.Key.alt_l, keyboard.Key.alt_r
        ]
        
        if key in blocked_keys:
            return False
        
        allowed_special = [
            keyboard.Key.up, keyboard.Key.down, 
            keyboard.Key.left, keyboard.Key.right,
            keyboard.Key.tab, keyboard.Key.backspace,
            keyboard.Key.space, keyboard.Key.enter
        ]
        
        if key in allowed_special:
            return True
        
        if hasattr(key, 'char') and key.char is not None:
            return True
        
        return False
    
    def get_key_name(self, key):
        """获取按键名称"""
        try:
            if hasattr(key, 'char') and key.char is not None:
                return key.char
            
            special_keys = {
                keyboard.Key.space: "space",
                keyboard.Key.tab: "tab",
                keyboard.Key.backspace: "backspace",
                keyboard.Key.up: "up",
                keyboard.Key.down: "down",
                keyboard.Key.left: "left",
                keyboard.Key.right: "right",
                keyboard.Key.enter: "enter"
            }
            return special_keys.get(key, str(key))
        except:
            return str(key)
    
    def run_32key_config(self):
        """32key配置 - 必须录入恰好32个按键"""
        current_keys = []
        
        def on_press(key):
            nonlocal current_keys
            
            if key == keyboard.Key.enter:
                print("\n\n✓ 按Enter键，准备保存配置...")
                return False
                
            if key == keyboard.Key.backspace:
                print("\n\n⚠ 按Backspace键，清空重新录入...")
                current_keys = []
                print(f"已清空，重新开始录入 (0/32)")
                return True
                
            if not self.is_valid_key(key):
                return True
            
            key_name = self.get_key_name(key)
            
            if key_name in current_keys:
                print(f"\r⚠ 按键 '{key_name}' 已存在！({len(current_keys)}/32)", end="")
                return True
            
            current_keys.append(key_name)
            print(f"\r✓ 已录入: {len(current_keys)}/32 - {key_name}", end="")
            
            if len(current_keys) >= 32:
                print("\n\n✓ 已达到32个按键，自动完成")
                return False
            
            return True
        
        while True:
            current_keys = []
            print("\n\n开始录入32个按键...")
            print("  - Enter: 保存  - Backspace: 清空  - 自动过滤功能键")
            print("  ⚠ 注意: 必须录入恰好32个按键才能保存")
            print("-" * 40)
            
            with keyboard.Listener(on_press=on_press) as listener:
                listener.join()
            
            # 检查按键数量是否为32
            if len(current_keys) != 32:
                print(f"\n❌ 按键数量不正确！当前 {len(current_keys)} 个，需要恰好 32 个")
                print("按 Backspace 重新录入，按 Enter 继续")
                
                decision = None
                def on_decision(key):
                    nonlocal decision
                    if key == keyboard.Key.backspace:
                        decision = "restart"
                        return False
                    elif key == keyboard.Key.enter:
                        decision = "continue"
                        return False
                    return True
                
                with keyboard.Listener(on_press=on_decision) as listener:
                    listener.join()
                
                if decision == "restart":
                    continue
                else:
                    continue
            
            # 显示确认
            print("\n" + "=" * 40)
            for idx, key in enumerate(current_keys[:32], 1):
                print(f"  按键 {idx:2d} → {key}")
            print("=" * 40)
            print("按 Enter 确认保存，Backspace 重新录入")
            
            confirmed = None
            def on_confirm(key):
                nonlocal confirmed
                if key == keyboard.Key.enter:
                    confirmed = True
                    return False
                elif key == keyboard.Key.backspace:
                    confirmed = False
                    return False
                return True
            
            with keyboard.Listener(on_press=on_confirm) as listener:
                listener.join()
            
            if confirmed:
                self.config["32key"]["keys"] = {str(i+1): current_keys[i] for i in range(32)}
                self.config_modified = True
                break
            else:
                print("重新开始录入...")
    
    def run_16key_config(self):
        """16key配置 - 必须录入恰好16个按键"""
        current_keys = []
        
        def on_press(key):
            nonlocal current_keys
            
            if key == keyboard.Key.enter:
                print("\n\n✓ 按Enter键，准备保存...")
                return False
                
            if key == keyboard.Key.backspace:
                print("\n\n⚠ 清空重新录入...")
                current_keys = []
                print("已清空 (0/16)")
                return True
                
            if not self.is_valid_key(key):
                return True
            
            key_name = self.get_key_name(key)
            
            if key_name in current_keys:
                print(f"\r⚠ '{key_name}' 已存在 ({len(current_keys)}/16)", end="")
                return True
            
            current_keys.append(key_name)
            print(f"\r✓ 已录入: {len(current_keys)}/16 - {key_name}", end="")
            
            if len(current_keys) >= 16:
                print("\n\n✓ 已达到16个按键，自动完成")
                return False
            
            return True
        
        while True:
            current_keys = []
            print("\n\n开始录入16个按键...")
            print("  - Enter: 保存  - Backspace: 清空")
            print("  ⚠ 注意: 必须录入恰好16个按键才能保存")
            print("-" * 40)
            
            with keyboard.Listener(on_press=on_press) as listener:
                listener.join()
            
            # 检查按键数量是否为16
            if len(current_keys) != 16:
                print(f"\n❌ 按键数量不正确！当前 {len(current_keys)} 个，需要恰好 16 个")
                print("按 Backspace 重新录入，按 Enter 继续")
                
                decision = None
                def on_decision(key):
                    nonlocal decision
                    if key == keyboard.Key.backspace:
                        decision = "restart"
                        return False
                    elif key == keyboard.Key.enter:
                        decision = "continue"
                        return False
                    return True
                
                with keyboard.Listener(on_press=on_decision) as listener:
                    listener.join()
                
                if decision == "restart":
                    continue
                else:
                    continue
            
            # 显示确认
            print("\n" + "=" * 40)
            for idx, key in enumerate(current_keys, 1):
                print(f"  按键 {idx:2d} → {key}")
            print("=" * 40)
            print("按 Enter 确认保存，Backspace 重新录入")
            
            confirmed = None
            def on_confirm(key):
                nonlocal confirmed
                if key == keyboard.Key.enter:
                    confirmed = True
                    return False
                elif key == keyboard.Key.backspace:
                    confirmed = False
                    return False
                return True
            
            with keyboard.Listener(on_press=on_confirm) as listener:
                listener.join()
            
            if confirmed:
                self.config["16key"]["keys"] = {str(i+1): current_keys[i] for i in range(16)}
                self.config_modified = True
                break
            else:
                print("重新开始...")
    
    def run_air_config(self):
        """Air模式配置（无上限，至少1个）"""
        current_keys = []
        
        def on_press(key):
            nonlocal current_keys
            
            if key == keyboard.Key.enter:
                print("\n\n✓ 按Enter键，准备保存...")
                return False
                
            if key == keyboard.Key.backspace:
                print("\n\n⚠ 清空重新录入...")
                current_keys = []
                print("已清空")
                return True
                
            if not self.is_valid_key(key):
                return True
            
            key_name = self.get_key_name(key)
            
            if key_name in current_keys:
                print(f"\r⚠ '{key_name}' 已存在 ({len(current_keys)}个)", end="")
                return True
            
            current_keys.append(key_name)
            print(f"\r✓ 已录入: {len(current_keys)}个 - {key_name}", end="")
            return True
        
        while True:
            current_keys = []
            print("\n\n开始录入Air模式按键（无上限，至少1个）...")
            print("  - Enter: 保存  - Backspace: 清空")
            print("-" * 40)
            
            with keyboard.Listener(on_press=on_press) as listener:
                listener.join()
            
            if len(current_keys) == 0:
                print("\n❌ 至少需要1个按键！")
                print("按 Backspace 重新录入")
                def on_backspace(key):
                    if key == keyboard.Key.backspace:
                        return False
                    return True
                with keyboard.Listener(on_press=on_backspace) as listener:
                    listener.join()
                continue
            
            print("\n" + "=" * 40)
            for idx, key in enumerate(current_keys, 1):
                print(f"  按键 {idx:2d} → {key}")
            print(f"\n总计: {len(current_keys)} 个按键")
            print("=" * 40)
            print("按 Enter 确认，Backspace 重新录入")
            
            confirmed = None
            def on_confirm(key):
                nonlocal confirmed
                if key == keyboard.Key.enter:
                    confirmed = True
                    return False
                elif key == keyboard.Key.backspace:
                    confirmed = False
                    return False
                return True
            
            with keyboard.Listener(on_press=on_confirm) as listener:
                listener.join()
            
            if confirmed:
                self.config["air"]["keys"] = {str(i+1): current_keys[i] for i in range(len(current_keys))}
                self.config_modified = True
                break
            else:
                print("重新开始...")
    
    def configure_mode(self, mode):
        """配置未完成的模式"""
        print(f"\n开始配置 {mode} 模式...")
        
        if mode != "air":
            while True:
                print("\n" + "=" * 40)
                print(f"      {mode}模式 - 缩限模式设置")
                print("=" * 40)
                print("缩限模式开启后，将限制按键的输入范围")
                print("1. 开启缩限模式")
                print("2. 关闭缩限模式")
                print("=" * 40)
                
                choice = input("请选择 (1/2): ").strip()
                
                if choice == "1":
                    self.config[mode]["limit"] = True
                    self.config_modified = True
                    print("✓ 已开启缩限模式")
                    break
                elif choice == "2":
                    self.config[mode]["limit"] = False
                    self.config_modified = True
                    print("✓ 已关闭缩限模式")
                    break
                else:
                    print("❌ 无效选择")
        
        if mode == "32key":
            self.run_32key_config()
        elif mode == "16key":
            self.run_16key_config()
        else:
            self.run_air_config()
        
        self.config[mode]["completed"] = True
        self.config_modified = True
        self.save_config()
    
    def modify_existing_mode(self, mode):
        """修改已完成的模式配置"""
        print(f"\n开始修改 {mode} 模式...")
        
        print("\n当前按键映射:")
        keys = self.config[mode]["keys"]
        for idx, key in keys.items():
            print(f"  按键 {idx:3s} → {key}")
        
        print("\n" + "=" * 40)
        print("请选择要修改的内容:")
        print("1. 修改按键映射")
        if mode != "air":
            print("2. 修改缩限模式设置")
        print("3. 返回上一级")
        print("=" * 40)
        
        modify_choice = input("请选择 (1/2/3): ").strip()
        
        if modify_choice == "3":
            print("返回上级菜单")
            return
        
        if modify_choice == "1":
            print("\n开始重新配置按键映射...")
            self.config[mode]["keys"] = {}
            self.config[mode]["completed"] = False
            
            if mode == "32key":
                self.run_32key_config()
            elif mode == "16key":
                self.run_16key_config()
            else:
                self.run_air_config()
            
            self.config[mode]["completed"] = True
            self.config_modified = True
            self.save_config()
            print(f"\n✓ {mode} 模式按键映射已更新")
        
        elif modify_choice == "2" and mode != "air":
            print("\n保持当前按键映射，只修改缩限模式设置")
            
            while True:
                print("\n" + "=" * 40)
                print(f"      {mode}模式 - 缩限模式设置")
                print("=" * 40)
                print("缩限模式开启后，将限制按键的输入范围")
                print(f"当前: {'开启' if self.config[mode]['limit'] else '关闭'}")
                print("1. 开启缩限模式 (true)")
                print("2. 关闭缩限模式 (false)")
                print("3. 保持不变并返回")
                print("=" * 40)
                
                choice = input("请选择 (1/2/3): ").strip()
                
                if choice == "1":
                    if self.config[mode]["limit"] != True:
                        self.config[mode]["limit"] = True
                        self.config_modified = True
                        print("✓ 已开启缩限模式")
                    else:
                        print("✓ 缩限模式已经是开启状态")
                    break
                elif choice == "2":
                    if self.config[mode]["limit"] != False:
                        self.config[mode]["limit"] = False
                        self.config_modified = True
                        print("✓ 已关闭缩限模式")
                    else:
                        print("✓ 缩限模式已经是关闭状态")
                    break
                elif choice == "3":
                    print("保持不变，返回")
                    break
                else:
                    print("❌ 无效选择")
            
            if self.config_modified:
                self.save_config()
            else:
                print("\n未检测到任何修改")
        
        else:
            print("❌ 无效选择")
    
    def select_active_mode(self):
        """选择激活模式 - 如果只有一个已完成则自动选择"""
        completed_modes = []
        if self.config["32key"]["completed"]:
            completed_modes.append("32key")
        if self.config["16key"]["completed"]:
            completed_modes.append("16key")
        if self.config["air"]["completed"]:
            completed_modes.append("air")
        
        if len(completed_modes) == 1:
            mode = completed_modes[0]
            self.config["active_mode"] = mode
            self.config_modified = True
            self.save_config()
            print(f"\n✓ 自动选择 {mode} 模式")
            return mode
        
        while True:
            print("\n" + "=" * 50)
            print("      选择要使用的模式")
            print("=" * 50)
            
            status_32 = "✓ 已完成" if self.config["32key"]["completed"] else "✗ 未完成"
            status_16 = "✓ 已完成" if self.config["16key"]["completed"] else "✗ 未完成"
            status_air = "✓ 已完成" if self.config["air"]["completed"] else "✗ 未完成"
            
            print(f"1. 32key模式 ({status_32})")
            print(f"2. 16key模式 ({status_16})")
            print(f"3. Air模式 ({status_air}, 无按键上限)")
            print("4. 退出程序")
            print("=" * 50)
            
            choice = input("请选择 (1/2/3/4): ").strip()
            
            if choice == "1" and self.config["32key"]["completed"]:
                self.config["active_mode"] = "32key"
                self.config_modified = True
                self.save_config()
                print(f"\n✓ 已切换到 32key 模式")
                return "32key"
            elif choice == "2" and self.config["16key"]["completed"]:
                self.config["active_mode"] = "16key"
                self.config_modified = True
                self.save_config()
                print(f"\n✓ 已切换到 16key 模式")
                return "16key"
            elif choice == "3" and self.config["air"]["completed"]:
                self.config["active_mode"] = "air"
                self.config_modified = True
                self.save_config()
                print(f"\n✓ 已切换到 Air 模式")
                return "air"
            elif choice == "4":
                return None
            else:
                print("❌ 无效选择，请输入 1、2、3 或 4")
    
    def run(self):
        """运行配置流程"""
        print("=== 按键配置工具 ===")
        print(f"配置文件: {self.config_file}")
        
        if not self.load_config():
            print("配置文件不存在，将创建新配置")
        
        self.show_status()
        
        # 检查是否有任何模式已完成
        has_completed = (self.config["32key"]["completed"] or 
                         self.config["16key"]["completed"] or 
                         self.config["air"]["completed"])
        
        if not has_completed:
            print("\n未检测到任何有效配置，请先配置一个模式")
            print("\n选择要配置的模式：")
            print("1. 32key模式 (需要32个按键)")
            print("2. 16key模式 (需要16个按键)")
            print("3. Air模式 (至少1个按键)")
            mode_choice = input("请选择 (1/2/3): ").strip()
            
            if mode_choice == "1":
                self.configure_mode("32key")
            elif mode_choice == "2":
                self.configure_mode("16key")
            elif mode_choice == "3":
                self.configure_mode("air")
            else:
                print("无效选择，程序退出")
                return None
        else:
            modify = input("\n是否修改配置？(y/n): ").strip().lower()
            if modify == 'y':
                print("\n选择要修改的内容：")
                print("1. 修改按键配置 (32key/16key/Air模式)")
                print("2. 修改校准数据")
                print("3. 返回")
                modify_choice = input("请选择 (1/2/3): ").strip()
                
                if modify_choice == "1":
                    print("\n选择要修改的模式：")
                    print("1. 32key模式 (需要32个按键)")
                    print("2. 16key模式 (需要16个按键)")
                    print("3. Air模式 (至少1个按键)")
                    mode_choice = input("请选择 (1/2/3): ").strip()
                    
                    if mode_choice == "1":
                        if self.config["32key"]["completed"]:
                            self.modify_existing_mode("32key")
                        else:
                            self.configure_mode("32key")
                    elif mode_choice == "2":
                        if self.config["16key"]["completed"]:
                            self.modify_existing_mode("16key")
                        else:
                            self.configure_mode("16key")
                    elif mode_choice == "3":
                        if self.config["air"]["completed"]:
                            self.modify_existing_mode("air")
                        else:
                            self.configure_mode("air")
                    else:
                        print("无效选择")
                
                elif modify_choice == "2":
                    print("\n修改校准数据需要重新连接设备进行校准")
                    confirm = input("是否现在进行校准？(y/n): ").strip().lower()
                    if confirm == 'y':
                        return "calibration_only"
                    else:
                        print("取消校准数据修改")
                
                elif modify_choice == "3":
                    print("返回")
                else:
                    print("无效选择")
        
        active_mode = self.select_active_mode()
        return active_mode


# ==================== 校准相关函数 ====================
def display_status(step):
    """显示当前状态"""
    print("\n" + "-" * 50)
    if step == 1:
        print("第一步校准 - 垂直偏移 (Y轴)")
        print(f"当前垂直偏移: {vertical_offset}")
    else:
        print("第二步校准 - 水平偏移 (X轴)")
        print(f"当前水平偏移: {horizontal_offset} (向内收缩)")
    
    print(f"左下角: {current_bottom_left}")
    print(f"右下角: {current_bottom_right}")
    print("-" * 50)
    print("控制说明:")
    if step == 1:
        print("  - 键: 下移    = 键: 上移")
    else:
        print("  - 键: 向内收缩    = 键: 向外扩张")
    print("  Backspace: 归零")
    print("  Enter: 确认并继续")
    print("-" * 50)


def handle_long_press(key_char, step, is_press):
    """处理长按逻辑"""
    global vertical_offset, horizontal_offset
    
    current_time = time.time()
    
    if is_press:
        key_press_times[key_char] = current_time
        
        def check_long_press():
            if key_char not in key_press_times:
                return
            press_start = key_press_times[key_char]
            time.sleep(LONG_PRESS_DELAY)
            
            if key_char in key_press_times and key_press_times[key_char] == press_start:
                while key_char in key_press_times and key_press_times[key_char] == press_start:
                    if step == 1:
                        if key_char == '-':
                            vertical_offset += 1
                            update_current_coordinates()
                            display_status(step)
                        elif key_char == '=':
                            if vertical_offset > 0:
                                vertical_offset -= 1
                            update_current_coordinates()
                            display_status(step)
                    else:
                        if key_char == '-':
                            horizontal_offset += 1
                            update_current_coordinates()
                            display_status(step)
                        elif key_char == '=':
                            if horizontal_offset > 0:
                                horizontal_offset -= 1
                            update_current_coordinates()
                            display_status(step)
                    
                    time.sleep(LONG_PRESS_INTERVAL)
        
        threading.Thread(target=check_long_press, daemon=True).start()
    else:
        if key_char in key_press_times:
            del key_press_times[key_char]


def calibration_step1():
    """第一步校准：垂直偏移"""
    global vertical_offset, stop_clicking
    
    print("\n" + "=" * 50)
    print("开始第一步校准：垂直偏移（上下调整）")
    print("=" * 50)
    
    vertical_offset = 0
    update_current_coordinates()
    display_status(1)
    
    stop_clicking = False
    click_thread = threading.Thread(target=clicking_loop, daemon=True)
    click_thread.start()
    
    def on_press(key):
        global vertical_offset, stop_clicking
        
        try:
            if key == keyboard.Key.enter:
                print("\n✓ 确认垂直偏移")
                stop_clicking = True
                return False
            
            elif key == keyboard.Key.backspace:
                vertical_offset = 0
                update_current_coordinates()
                display_status(1)
                print("✓ 已归零")
            
            elif hasattr(key, 'char') and key.char in ['-', '=']:
                handle_long_press(key.char, 1, True)
                if key.char == '-':
                    vertical_offset += 1
                    update_current_coordinates()
                    display_status(1)
                elif key.char == '=':
                    if vertical_offset > 0:
                        vertical_offset -= 1
                    update_current_coordinates()
                    display_status(1)
        
        except Exception as e:
            print(f"键盘错误: {e}")
    
    def on_release(key):
        try:
            if hasattr(key, 'char') and key.char in ['-', '=']:
                handle_long_press(key.char, 1, False)
        except:
            pass
    
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
    
    time.sleep(0.5)
    print("第一步校准完成\n")


def calibration_step2():
    """第二步校准：水平偏移"""
    global horizontal_offset, stop_clicking
    
    print("\n" + "=" * 50)
    print("开始第二步校准：水平偏移（左右向内收缩/向外扩张）")
    print("=" * 50)
    
    horizontal_offset = 0
    update_current_coordinates()
    display_status(2)
    
    stop_clicking = False
    click_thread = threading.Thread(target=clicking_loop, daemon=True)
    click_thread.start()
    
    def on_press(key):
        global horizontal_offset, stop_clicking
        
        try:
            if key == keyboard.Key.enter:
                print("\n✓ 确认水平偏移")
                stop_clicking = True
                return False
            
            elif key == keyboard.Key.backspace:
                horizontal_offset = 0
                update_current_coordinates()
                display_status(2)
                print("✓ 已归零")
            
            elif hasattr(key, 'char') and key.char in ['-', '=']:
                handle_long_press(key.char, 2, True)
                if key.char == '-':
                    horizontal_offset += 1
                    update_current_coordinates()
                    display_status(2)
                elif key.char == '=':
                    if horizontal_offset > 0:
                        horizontal_offset -= 1
                    update_current_coordinates()
                    display_status(2)
        
        except Exception as e:
            print(f"键盘错误: {e}")
    
    def on_release(key):
        try:
            if hasattr(key, 'char') and key.char in ['-', '=']:
                handle_long_press(key.char, 2, False)
        except:
            pass
    
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
    
    time.sleep(0.5)
    print("第二步校准完成\n")


def run_calibration(config_manager):
    """运行校准流程"""
    global device
    
    print("\n=== 键盘校准工具 ===")
    print(f"配置: 点击间隔={CLICK_INTERVAL*1000:.1f}ms, 屏幕留白={SCREEN_MARGIN}px\n")
    
    if not connect_adb():
        print("无法连接设备，程序退出")
        return False
    
    get_screen_size()
    
    if not init_coordinates():
        print("初始化坐标失败")
        return False
    
    update_current_coordinates()
    
    calibration_step1()
    calibration_step2()
    
    # 保存校准数据到 config_manager
    config_manager.save_calibration(current_bottom_left, current_bottom_right)
    
    print("\n校准完成！")
    return True


# ==================== 主程序 ====================
def main():
    print("=== 一体化配置工具 ===\n")
    
    # 第一步：运行配置管理
    config_manager = KeyConfigManager()
    result = config_manager.run()
    
    # 如果返回 "calibration_only"，表示只进行校准
    if result == "calibration_only":
        print("\n" + "=" * 60)
        print("进入校准阶段")
        print("=" * 60)
        if run_calibration(config_manager):
            print("\n✓ 校准完成！")
            print(f"  配置文件: {CONFIG_FILE}")
        else:
            print("\n校准失败，请检查设备连接")
        return
    
    if result is None:
        print("\n程序退出")
        return
    
    active_mode = result
    
    # 第二步：运行校准
    print("\n" + "=" * 60)
    print("配置完成，进入校准阶段")
    print("=" * 60)
    
    if run_calibration(config_manager):
        print("\n✓ 全部完成！")
        print(f"  配置文件: {CONFIG_FILE}")
        print(f"  激活模式: {active_mode}")
    else:
        print("\n校准失败，请检查设备连接")


if __name__ == "__main__":
    main()