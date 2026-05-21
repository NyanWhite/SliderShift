import json
import time
import threading
import sys
import re
import subprocess
from ppadb.client import Client as AdbClient

# ==================== 全局配置参数 ====================
# ADB 点击间隔（秒），越小点击越快，但可能被系统限频
CLICK_INTERVAL = 0.008  # 默认 0.008 秒，如果系统检测不到可适当调大（如 0.015）

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
KEYBOARD_CONFIG_FILE = "keyboard.json"

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


def get_adb_path():
    """获取 adb 可执行文件路径，优先使用当前目录下的 adb.exe"""
    import os
    current_dir_adb = os.path.join(os.path.dirname(sys.argv[0]), "adb.exe")
    if os.path.exists(current_dir_adb):
        return current_dir_adb
    cwd_adb = os.path.join(os.getcwd(), "adb.exe")
    if os.path.exists(cwd_adb):
        return cwd_adb
    return "adb"


def run_adb_command(args, timeout=ADB_TIMEOUT):
    """执行 adb 命令 - 修复编码问题"""
    adb_path = get_adb_path()
    try:
        result = subprocess.run(
            [adb_path] + args,
            capture_output=True,
            text=True,
            encoding='utf-8',  # 强制使用 utf-8
            errors='replace',   # 忽略编码错误
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
    """获取屏幕分辨率 - 使用多种方式检测横屏"""
    global screen_width, screen_height
    
    print("正在获取屏幕分辨率...")
    while True:
        try:
            # 方式1: 获取物理分辨率
            result = device.shell("wm size")
            if result:
                match = re.search(r'(\d+)x(\d+)', result)
                if match:
                    screen_width = int(match.group(1))
                    screen_height = int(match.group(2))
                    print(f"物理分辨率: {screen_width} x {screen_height}")
            
            # 方式2: 获取当前显示方向
            rotation_result = device.shell("dumpsys input | grep 'SurfaceOrientation'")
            if not rotation_result:
                rotation_result = device.shell("settings get system user_rotation")
            
            # 解析旋转角度
            rotation = 0
            if rotation_result:
                # 查找数字
                rot_match = re.search(r'(\d+)', rotation_result)
                if rot_match:
                    rotation = int(rot_match.group(1))
            
            # 根据旋转角度判断实际宽高
            # rotation: 0=竖屏, 1=横屏(右转90°), 2=反向竖屏, 3=横屏(左转90°)
            is_landscape = (rotation == 1 or rotation == 3)
            
            if is_landscape:
                # 如果当前是横屏但物理分辨率是竖屏，需要交换宽高
                if screen_width < screen_height:
                    screen_width, screen_height = screen_height, screen_width
                print(f"✓ 横屏模式 (旋转角度: {rotation * 90}°)")
                print(f"  实际使用分辨率: {screen_width} x {screen_height}\n")
            else:
                print(f"⚠️  提示: 当前为竖屏模式 (旋转角度: {rotation * 90}°)，建议切换到横屏以获得最佳体验")
                print(f"  物理分辨率: {screen_width} x {screen_height}\n")
            
            # 确保宽高正确（宽>高为横屏）
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
    
    # 使用配置的留白，设为0则贴边
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
    """获取连接地址 - 完全独立的输入函数"""
    print("\n" + "=" * 50)
    print("步骤2: 连接设备")
    print("请查看手机无线调试页面中的「连接端口」")
    print("注意：连接端口通常与配对端口不同！")
    print("=" * 50)
    
    # 等待并清理
    time.sleep(0.5)
    
    # 强制刷新所有缓冲区
    sys.stdout.flush()
    sys.stdin.flush()
    
    # 在 Windows 下，使用 msvcrt 完全清空输入缓冲区
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()
    except:
        pass
    
    # 直接使用 input，不做任何额外处理
    result = input("请输入连接地址: ").strip()
    return result


def adb_pair(pair_ip, pair_code):
    """独立的 ADB 配对函数 - 使用 subprocess 并正确处理编码"""
    adb_path = get_adb_path()
    
    try:
        # 使用 subprocess 但正确设置编码
        proc = subprocess.Popen(
            [adb_path, "pair", pair_ip],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',  # 强制使用 utf-8
            errors='replace'   # 忽略编码错误
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
    """使用配对码方式连接无线 ADB - 修复版本"""
    
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
            # 传统配对码方式
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
            
            # 调用配对函数
            if not adb_pair(pair_ip, pair_code):
                retry = input("是否重试？(y/n): ").strip().lower()
                if retry != 'y':
                    continue
            
            # 配对成功后，等待用户输入连接地址
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
            
            # 检查是否包含端口号
            if ":" not in connect_ip_port:
                print("错误：连接地址必须包含端口号，例如 192.168.137.127:43267")
                continue
            
            print(f"正在连接 {connect_ip_port} ...")
            result = run_adb_command(["connect", connect_ip_port])
            
            # 安全地检查结果
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
            # 直接输入已连接的设备地址
            print("\n直接连接模式 (跳过配对)")
            print("注意：需要输入完整的连接地址，包含端口号")
            print("例如：192.168.137.127:43267")
            
            connect_ip_port = input("请输入连接地址: ").strip()
            if not connect_ip_port:
                print("连接地址不能为空")
                continue
            
            # 检查是否包含端口号
            if ":" not in connect_ip_port:
                print("错误：连接地址必须包含端口号，例如 192.168.137.127:43267")
                continue
            
            print(f"正在连接 {connect_ip_port} ...")
            result = run_adb_command(["connect", connect_ip_port])
            
            # 安全地检查结果
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
                # 尝试查找已连接的设备
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
    """连接 ADB 设备 - 自动重连优先，无线使用配对码方式"""
    global device
    
    print("\n正在连接 ADB 设备...")
    
    # 确保 ADB 服务器运行
    run_adb_command(["start-server"])
    
    # 获取已知设备列表
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
    
    # 1. 优先检查有线 USB 设备
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
    
    # 2. 没有 USB 设备，尝试自动重连已知的无线设备
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
    
    # 3. 没有可用设备，让用户选择连接方式
    print("\n未找到已连接的设备")
    result_tuple = connect_adb_pairing()
    
    # 检查返回值类型
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


def display_status(step):
    """显示当前状态"""
    print("\n" + "=" * 50)
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
    print("=" * 50)


def save_keyboard_config():
    """保存键盘校准数据到 JSON 文件"""
    config = {
        "keyboard_left": list(current_bottom_left),
        "keyboard_right": list(current_bottom_right)
    }
    try:
        with open(KEYBOARD_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"\n✓ 校准数据已保存至 {KEYBOARD_CONFIG_FILE}")
        print(f"  左下角: {current_bottom_left}")
        print(f"  右下角: {current_bottom_right}")
    except Exception as e:
        print(f"保存配置文件失败: {e}")


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
    from pynput import keyboard  # 延迟导入，避免干扰 input()
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
    from pynput import keyboard  # 延迟导入，避免干扰 input()
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


def main():
    global device
    
    print("=== 键盘校准工具 ===")
    print(f"配置: 点击间隔={CLICK_INTERVAL*1000:.1f}ms, 屏幕留白={SCREEN_MARGIN}px\n")
    
    if not connect_adb():
        print("无法连接设备，程序退出")
        return
    
    get_screen_size()
    
    if not init_coordinates():
        print("初始化坐标失败")
        return
    
    update_current_coordinates()
    
    calibration_step1()
    calibration_step2()
    
    save_keyboard_config()
    
    print("\n校准完成！")


if __name__ == "__main__":
    main()