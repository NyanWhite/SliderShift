#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
import math
import time
import subprocess
import re
import random
from pynput import keyboard
from ppadb.client import Client as AdbClient


# ==================== 全局配置 ====================
CONFIG_FILE = "config.json"
INPUT_FILE = "input.json"

# ADB 相关配置
ADB_TIMEOUT = 10
RESOLUTION_RETRY_DELAY = 2

# 全局变量
device = None
stop_connecting = False  # 用于中断连接循环
stop_listener = False     # 用于中断键盘监听
key_positions = {}        # 存储每个按键对应的 (x, y) 坐标

# 运行时参数（从 input.json 加载）
runtime_config = {
    "sel_range": 0.0,
    "sliding_simulate": False,
    "randomize_range": "0,0",
    "hold_duration": 0.05,
    "hz_rate": 120
}

# 按键按下时间记录（用于长按检测）
key_press_times = {}


# ==================== 配置文件检查 ====================
def check_config_completeness():
    """检查 config.json 完整性"""
    
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ 错误: 配置文件 '{CONFIG_FILE}' 不存在!")
        print("请先运行 ConfigSetting.py 进行配置")
        return False, None, None
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ 错误: 无法读取配置文件 '{CONFIG_FILE}'!")
        print(f"   详细信息: {e}")
        return False, None, None
    
    print("=" * 60)
    print("           配置文件完整性检查")
    print("=" * 60)
    
    errors = []
    
    # 1. 检查 air 模式 (必须完成)
    air_completed = config.get("air", {}).get("completed", False)
    air_keys = config.get("air", {}).get("keys", {})
    air_key_count = len(air_keys)
    
    if air_completed and air_key_count > 0:
        print(f"✓ Air模式: 已完成 ({air_key_count} 个按键)")
    else:
        print(f"✗ Air模式: 未完成 (需要至少1个按键)")
        errors.append("Air模式配置不完整，请运行 ConfigSetting.py 重新配置 Air 模式")
    
    # 2. 检查 32key 和 16key (至少一个完成)
    mode32_completed = config.get("32key", {}).get("completed", False)
    mode32_key_count = len(config.get("32key", {}).get("keys", {}))
    mode16_completed = config.get("16key", {}).get("completed", False)
    mode16_key_count = len(config.get("16key", {}).get("keys", {}))
    
    print(f"✓ 32key模式: {'已完成' if mode32_completed else '未完成'} ({mode32_key_count} 个按键)")
    print(f"✓ 16key模式: {'已完成' if mode16_completed else '未完成'} ({mode16_key_count} 个按键)")
    
    if not mode32_completed and not mode16_completed:
        print(f"✗ 错误: 32key 和 16key 都未完成!")
        errors.append("32key 和 16key 至少需要完成一个，请运行 ConfigSetting.py 进行配置")
    
    # 3. 检查校准数据
    calibration = config.get("calibration", {})
    left = calibration.get("keyboard_left", [0, 0])
    right = calibration.get("keyboard_right", [0, 0])
    
    left_valid = (left[0] != 0 or left[1] != 0)
    right_valid = (right[0] != 0 or right[1] != 0)
    
    if left_valid and right_valid:
        print(f"✓ 校准数据: 已完成")
        print(f"   左下角: ({left[0]}, {left[1]})")
        print(f"   右下角: ({right[0]}, {right[1]})")
    else:
        print(f"✗ 校准数据: 未完成")
        errors.append("校准数据不完整，请运行 ConfigSetting.py 重新进行校准")
    
    print("=" * 60)
    
    if errors:
        print("\n❌ 配置文件检查失败! 存在以下问题:")
        for err in errors:
            print(f"   - {err}")
        print("\n请运行 ConfigSetting.py 完成配置后重试")
        return False, None, None
    
    print("\n✅ 配置文件完整!")
    
    # 确定使用的模式
    selected_mode = None
    if mode32_completed and mode16_completed:
        print("\n检测到 32key 和 16key 模式都已完成")
        while True:
            choice = input("请选择要使用的模式 (1=32key, 2=16key): ").strip()
            if choice == "1":
                selected_mode = "32key"
                break
            elif choice == "2":
                selected_mode = "16key"
                break
            else:
                print("❌ 无效选择，请输入 1 或 2")
    elif mode32_completed:
        selected_mode = "32key"
        print(f"\n✓ 自动选择 32key 模式")
    elif mode16_completed:
        selected_mode = "16key"
        print(f"\n✓ 自动选择 16key 模式")
    
    print(f"当前激活模式: {selected_mode}")
    
    return True, config, selected_mode


# ==================== input.json 管理 ====================
def validate_and_fix_input_config(config):
    """验证并修复 input.json 配置参数"""
    DEFAULT_CONFIG = {
        "sel_range": 0.0,
        "sliding_simulate": False,
        "randomize_range": "0,0",
        "hold_duration": 0.05,
        "hz_rate": 120
    }
    
    modified = False
    errors = []
    
    # 1. 检查 sel_range (≥0)
    if "sel_range" not in config:
        config["sel_range"] = DEFAULT_CONFIG["sel_range"]
        errors.append("sel_range 缺失，已设置为默认值 0.0")
        modified = True
    else:
        try:
            val = float(config["sel_range"])
            if val < 0:
                config["sel_range"] = DEFAULT_CONFIG["sel_range"]
                errors.append("sel_range 不能为负数，已重置为默认值 0.0")
                modified = True
            else:
                config["sel_range"] = val
        except (ValueError, TypeError):
            config["sel_range"] = DEFAULT_CONFIG["sel_range"]
            errors.append("sel_range 格式错误，已重置为默认值 0.0")
            modified = True
    
    # 2. 检查 sliding_simulate
    if "sliding_simulate" not in config:
        config["sliding_simulate"] = DEFAULT_CONFIG["sliding_simulate"]
        errors.append("sliding_simulate 缺失，已设置为默认值 false")
        modified = True
    else:
        if isinstance(config["sliding_simulate"], str):
            if config["sliding_simulate"].lower() in ["true", "1", "yes", "on"]:
                config["sliding_simulate"] = True
                modified = True
            elif config["sliding_simulate"].lower() in ["false", "0", "no", "off"]:
                config["sliding_simulate"] = False
                modified = True
            else:
                config["sliding_simulate"] = DEFAULT_CONFIG["sliding_simulate"]
                errors.append("sliding_simulate 格式错误，已重置为默认值 false")
                modified = True
        elif not isinstance(config["sliding_simulate"], bool):
            config["sliding_simulate"] = bool(config["sliding_simulate"])
            modified = True
    
    # 3. 检查 randomize_range
    if "randomize_range" not in config:
        config["randomize_range"] = DEFAULT_CONFIG["randomize_range"]
        errors.append("randomize_range 缺失，已设置为默认值 '0,0'")
        modified = True
    else:
        if isinstance(config["randomize_range"], list):
            if len(config["randomize_range"]) >= 2:
                try:
                    val1 = int(config["randomize_range"][0])
                    val2 = int(config["randomize_range"][1])
                    config["randomize_range"] = f"{val1},{val2}"
                    modified = True
                except (ValueError, TypeError):
                    config["randomize_range"] = DEFAULT_CONFIG["randomize_range"]
                    errors.append("randomize_range 列表值无效，已重置为默认值 '0,0'")
                    modified = True
            else:
                config["randomize_range"] = DEFAULT_CONFIG["randomize_range"]
                errors.append("randomize_range 列表长度不足，已重置为默认值 '0,0'")
                modified = True
        elif isinstance(config["randomize_range"], str):
            parts = config["randomize_range"].split(",")
            if len(parts) != 2:
                config["randomize_range"] = DEFAULT_CONFIG["randomize_range"]
                errors.append("randomize_range 格式错误（需要两个值，逗号分隔），已重置为默认值 '0,0'")
                modified = True
            else:
                try:
                    val1 = int(parts[0].strip())
                    val2 = int(parts[1].strip())
                    config["randomize_range"] = f"{val1},{val2}"
                except ValueError:
                    config["randomize_range"] = DEFAULT_CONFIG["randomize_range"]
                    errors.append("randomize_range 值必须是整数，已重置为默认值 '0,0'")
                    modified = True
        else:
            config["randomize_range"] = DEFAULT_CONFIG["randomize_range"]
            errors.append("randomize_range 格式错误，已重置为默认值 '0,0'")
            modified = True
    
    # 4. 检查 hold_duration (≥0)
    if "hold_duration" not in config:
        config["hold_duration"] = DEFAULT_CONFIG["hold_duration"]
        errors.append("hold_duration 缺失，已设置为默认值 0.05")
        modified = True
    else:
        try:
            val = float(config["hold_duration"])
            if val < 0:
                config["hold_duration"] = DEFAULT_CONFIG["hold_duration"]
                errors.append("hold_duration 不能为负数，已重置为默认值 0.05")
                modified = True
            else:
                config["hold_duration"] = val
        except (ValueError, TypeError):
            config["hold_duration"] = DEFAULT_CONFIG["hold_duration"]
            errors.append("hold_duration 格式错误，已重置为默认值 0.05")
            modified = True
    
    # 5. 检查 hz_rate (>0)
    if "hz_rate" not in config:
        config["hz_rate"] = DEFAULT_CONFIG["hz_rate"]
        errors.append("hz_rate 缺失，已设置为默认值 120")
        modified = True
    else:
        try:
            val = float(config["hz_rate"])
            if val <= 0:
                config["hz_rate"] = DEFAULT_CONFIG["hz_rate"]
                errors.append("hz_rate 必须大于0，已重置为默认值 120")
                modified = True
            else:
                if val.is_integer():
                    config["hz_rate"] = int(val)
                else:
                    config["hz_rate"] = val
        except (ValueError, TypeError):
            config["hz_rate"] = DEFAULT_CONFIG["hz_rate"]
            errors.append("hz_rate 格式错误，已重置为默认值 120")
            modified = True
    
    return config, modified, errors


def load_input_config():
    """加载 input.json 配置文件到 runtime_config"""
    global runtime_config
    
    if not os.path.exists(INPUT_FILE):
        print(f"⚠ 配置文件 '{INPUT_FILE}' 不存在，创建默认配置...")
        DEFAULT_CONFIG = {
            "sel_range": 0.0,
            "sliding_simulate": False,
            "randomize_range": "0,0",
            "hold_duration": 0.05,
            "hz_rate": 120
        }
        try:
            with open(INPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ 创建 {INPUT_FILE} 失败: {e}")
            return False
    
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ 读取 {INPUT_FILE} 失败: {e}")
        return False
    
    # 验证并修复
    fixed_config, modified, errors = validate_and_fix_input_config(config)
    
    if errors:
        for err in errors:
            print(f"⚠ {err}")
    
    if modified:
        try:
            with open(INPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(fixed_config, f, indent=2, ensure_ascii=False)
            print("✓ input.json 已自动修复")
        except Exception as e:
            print(f"❌ 保存 {INPUT_FILE} 失败: {e}")
            return False
    
    # 加载到 runtime_config
    runtime_config["sel_range"] = fixed_config.get("sel_range", 0.0)
    runtime_config["sliding_simulate"] = fixed_config.get("sliding_simulate", False)
    runtime_config["randomize_range"] = fixed_config.get("randomize_range", "0,0")
    runtime_config["hold_duration"] = fixed_config.get("hold_duration", 0.05)
    runtime_config["hz_rate"] = fixed_config.get("hz_rate", 120)
    
    return True


def save_input_config():
    """保存 runtime_config 到 input.json"""
    config = {
        "sel_range": runtime_config["sel_range"],
        "sliding_simulate": runtime_config["sliding_simulate"],
        "randomize_range": runtime_config["randomize_range"],
        "hold_duration": runtime_config["hold_duration"],
        "hz_rate": runtime_config["hz_rate"]
    }
    
    try:
        with open(INPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ 保存 {INPUT_FILE} 失败: {e}")
        return False


# ==================== 坐标计算 ====================
def find_closest_even(target):
    """找到最接近目标值的偶数"""
    lower_even = math.floor(target / 2) * 2
    upper_even = lower_even + 2
    
    if abs(lower_even - target) <= abs(upper_even - target):
        return int(lower_even)
    else:
        return int(upper_even)


def calculate_cell(distance):
    """计算 cell 值，找到最接近 distance/12 的偶数"""
    target = distance / 12
    cell = find_closest_even(target)
    return cell


def calculate_positions_16key_limit(calibration, cell):
    """16key 缩限模式开启"""
    left_x = calibration["keyboard_left"][0]
    y = calibration["keyboard_left"][1]
    
    cell_center = cell / 2
    
    positions = []
    current_x = left_x + cell_center + cell
    
    for i in range(12):
        positions.append((int(current_x), y))
        current_x += cell
    
    return positions


def calculate_positions_16key_normal(calibration):
    """16key 缩限模式关闭"""
    left_x = calibration["keyboard_left"][0]
    right_x = calibration["keyboard_right"][0]
    y = calibration["keyboard_left"][1]
    
    distance = right_x - left_x
    target = distance / 16
    segment_width = find_closest_even(target)
    
    positions = []
    current_x = left_x + segment_width / 2
    
    for i in range(16):
        positions.append((int(current_x), y))
        current_x += segment_width
    
    return positions


def calculate_positions_32key_limit(calibration, cell):
    """32key 缩限模式开启"""
    left_x = calibration["keyboard_left"][0]
    y = calibration["keyboard_left"][1]
    
    cell_center = cell / 2
    
    positions_top = []
    positions_bottom = []
    current_x = left_x + cell_center + cell
    
    for i in range(12):
        positions_top.append((int(current_x), y))
        positions_bottom.append((int(current_x), y))
        current_x += cell
    
    return positions_top, positions_bottom


def calculate_positions_32key_normal(calibration):
    """32key 缩限模式关闭"""
    left_x = calibration["keyboard_left"][0]
    right_x = calibration["keyboard_right"][0]
    y = calibration["keyboard_left"][1]
    
    distance = right_x - left_x
    target = distance / 16
    segment_width = find_closest_even(target)
    
    positions_top = []
    positions_bottom = []
    current_x = left_x + segment_width / 2
    
    for i in range(16):
        positions_top.append((int(current_x), y))
        positions_bottom.append((int(current_x), y))
        current_x += segment_width
    
    return positions_top, positions_bottom


def calculate_key_positions(config, selected_mode):
    """计算按键位置，返回 key_positions 字典"""
    global key_positions
    
    calibration = config.get("calibration", {})
    left_x = calibration["keyboard_left"][0]
    right_x = calibration["keyboard_right"][0]
    distance = right_x - left_x
    
    # 计算 cell
    cell = calculate_cell(distance)
    
    key_positions = {}
    
    if selected_mode == "16key":
        config_16key = config.get("16key", {})
        limit = config_16key.get("limit", False)
        keys = config_16key.get("keys", {})
        
        if limit:
            positions = calculate_positions_16key_limit(calibration, cell)
            for i, pos in enumerate(positions):
                key_index = i + 3
                key_name = keys.get(str(key_index), f"key{key_index}")
                key_positions[key_name] = pos
        else:
            positions = calculate_positions_16key_normal(calibration)
            for i, pos in enumerate(positions):
                key_index = i + 1
                key_name = keys.get(str(key_index), f"key{key_index}")
                key_positions[key_name] = pos
                
    elif selected_mode == "32key":
        config_32key = config.get("32key", {})
        limit = config_32key.get("limit", False)
        keys = config_32key.get("keys", {})
        
        top_keys = {}
        bottom_keys = {}
        for idx_str, key_name in keys.items():
            idx = int(idx_str)
            if idx <= 16:
                top_keys[idx] = key_name
            else:
                bottom_keys[idx] = key_name
        
        if limit:
            top_positions, bottom_positions = calculate_positions_32key_limit(calibration, cell)
            for i, pos in enumerate(top_positions):
                key_index = i + 3
                key_name = top_keys.get(str(key_index), f"key{key_index}")
                key_positions[key_name] = pos
            for i, pos in enumerate(bottom_positions):
                key_index = i + 19
                key_name = bottom_keys.get(str(key_index), f"key{key_index}")
                key_positions[key_name] = pos
        else:
            top_positions, bottom_positions = calculate_positions_32key_normal(calibration)
            for i, pos in enumerate(top_positions):
                key_index = i + 1
                key_name = top_keys.get(str(key_index), f"key{key_index}")
                key_positions[key_name] = pos
            for i, pos in enumerate(bottom_positions):
                key_index = i + 17
                key_name = bottom_keys.get(str(key_index), f"key{key_index}")
                key_positions[key_name] = pos
    
    return key_positions


# ==================== ADB 有线连接 ====================
def get_adb_path():
    """获取 adb 可执行文件路径"""
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


def connect_usb_adb():
    """连接 USB ADB 设备，持续尝试直到成功或用户按 Backspace"""
    global device, stop_connecting
    
    print("\n" + "=" * 60)
    print("           ADB 有线设备连接")
    print("=" * 60)
    print("请确保手机已通过 USB 连接到电脑")
    print("并已开启开发者选项和 USB 调试")
    print("\n提示: 按 Backspace 键可中断连接并返回主界面")
    print("-" * 60)
    
    # 启动 ADB 服务
    run_adb_command(["start-server"])
    
    # 启动键盘监听
    def on_press(key):
        global stop_connecting
        try:
            if key == keyboard.Key.backspace:
                print("\n⚠ 用户中断连接")
                stop_connecting = True
                return False
        except:
            pass
        return True
    
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    
    stop_connecting = False
    attempt = 0
    
    while not stop_connecting:
        attempt += 1
        print(f"\r正在检查设备... (尝试 {attempt})", end="", flush=True)
        
        result = run_adb_command(["devices"])
        
        if result and result.stdout:
            lines = result.stdout.strip().split('\n')[1:]
            for line in lines:
                if line.strip() and "device" in line:
                    serial = line.split()[0]
                    if ":" not in serial and not serial.startswith("adb-"):
                        print(f"\n\n✓ 发现 USB 设备: {serial}")
                        
                        adb = AdbClient(host="127.0.0.1", port=5037)
                        devices = adb.devices()
                        
                        for dev in devices:
                            if dev.serial == serial:
                                device = dev
                                listener.stop()
                                print("✓ ADB 连接成功!")
                                return True
        
        for _ in range(RESOLUTION_RETRY_DELAY):
            if stop_connecting:
                break
            time.sleep(1)
    
    listener.stop()
    return False


# ==================== 设置界面 ====================
def show_settings_menu():
    """显示设置菜单"""
    print("\n" + "=" * 50)
    print("              设置界面")
    print("=" * 50)
    print()
    print("1. Flick触发时参考的最后输入的Note的范围（s为单位）")
    print("   • 这将影响多flick时的运行表现，过低可能导致flick未被触发")
    print("   • 使用0以禁用，并只使用最后一个输入的note进行判定")
    print(f"   当前值: {runtime_config['sel_range']}")
    print()
    print("2. 使用滑动模拟")
    print("   • 如需开启 尽量不要快速同时输入大量按键（例如直接一排触发）")
    print("   • 这可能导致无法预料的事情发生")
    print("   • 开启后，模拟更加真实的游玩情况")
    print(f"   当前值: {runtime_config['sliding_simulate']}")
    print()
    print("3. 输入位置随机化")
    print("   • 在输入时对触摸位置进行随机化以更好的模拟真实游玩")
    print("   • 该值将影响全局触摸输入表现")
    print(f"   当前值: {runtime_config['randomize_range']}")
    print()
    print("4. Tap与Hold的状态转换")
    print("   • 超出此值，将输入状态转换为长按，位置不受随机化影响")
    print(f"   当前值: {runtime_config['hold_duration']}")
    print()
    print("5. 窗口刷新率")
    print("   • 将对齐运行时所有的采样间隔 刷新率 可以为小数")
    print(f"   当前值: {runtime_config['hz_rate']}")
    print()
    print("=" * 50)
    print("操作说明:")
    print("  - 输入数字(1-5)选择要修改的参数")
    print("  - 按 Backspace 保存并返回主程序")
    print("=" * 50)


def edit_sel_range():
    """修改 sel_range 参数"""
    print(f"\n当前值: {runtime_config['sel_range']}")
    print("请输入新值（≥0，按回车保持当前值）: ", end="")
    user_input = input().strip()
    
    if user_input == "":
        print("保持不变")
        return
    
    try:
        val = float(user_input)
        if val < 0:
            print("❌ 值不能为负数，保持不变")
        else:
            runtime_config["sel_range"] = val
            print(f"✓ 已设置为 {val}")
    except ValueError:
        print("❌ 输入无效，请输入数字")


def edit_sliding_simulate():
    """修改 sliding_simulate 参数"""
    print(f"\n当前值: {runtime_config['sliding_simulate']}")
    print("请输入 (Y/N，按回车保持当前值): ", end="")
    user_input = input().strip().lower()
    
    if user_input == "":
        print("保持不变")
        return
    
    if user_input in ["y", "yes", "true", "1", "on"]:
        runtime_config["sliding_simulate"] = True
        print("✓ 已设置为 True")
    elif user_input in ["n", "no", "false", "0", "off"]:
        runtime_config["sliding_simulate"] = False
        print("✓ 已设置为 False")
    else:
        print("❌ 输入无效，请输入 Y 或 N")


def edit_randomize_range():
    """修改 randomize_range 参数"""
    print(f"\n当前值: {runtime_config['randomize_range']}")
    print("请输入 (格式: x y，用空格分割，按回车保持当前值): ", end="")
    user_input = input().strip()
    
    if user_input == "":
        print("保持不变")
        return
    
    parts = user_input.split()
    if len(parts) != 2:
        print("❌ 输入无效，需要两个整数，用空格分割")
        return
    
    try:
        x = int(parts[0])
        y = int(parts[1])
        runtime_config["randomize_range"] = f"{x},{y}"
        print(f"✓ 已设置为 {x},{y}")
    except ValueError:
        print("❌ 输入无效，请输入整数")


def edit_hold_duration():
    """修改 hold_duration 参数"""
    print(f"\n当前值: {runtime_config['hold_duration']}")
    print("请输入新值（≥0，按回车保持当前值）: ", end="")
    user_input = input().strip()
    
    if user_input == "":
        print("保持不变")
        return
    
    try:
        val = float(user_input)
        if val < 0:
            print("❌ 值不能为负数，保持不变")
        else:
            runtime_config["hold_duration"] = val
            print(f"✓ 已设置为 {val}")
    except ValueError:
        print("❌ 输入无效，请输入数字")


def edit_hz_rate():
    """修改 hz_rate 参数"""
    print(f"\n当前值: {runtime_config['hz_rate']}")
    print("请输入新值（>0，按回车保持当前值）: ", end="")
    user_input = input().strip()
    
    if user_input == "":
        print("保持不变")
        return
    
    try:
        val = float(user_input)
        if val <= 0:
            print("❌ 值必须大于0，保持不变")
        else:
            if val.is_integer():
                runtime_config["hz_rate"] = int(val)
            else:
                runtime_config["hz_rate"] = val
            print(f"✓ 已设置为 {runtime_config['hz_rate']}")
    except ValueError:
        print("❌ 输入无效，请输入数字")


def run_settings():
    """运行设置界面"""
    while True:
        show_settings_menu()
        
        choice = input("\n请选择要修改的参数 (1-5) 或按 Backspace 返回: ").strip()
        
        if choice == "":
            # 检测 Backspace 需要通过特殊方式，这里用空字符串处理
            # 实际 Backspace 会返回空字符串
            pass
        
        if choice == "1":
            edit_sel_range()
            save_input_config()
        elif choice == "2":
            edit_sliding_simulate()
            save_input_config()
        elif choice == "3":
            edit_randomize_range()
            save_input_config()
        elif choice == "4":
            edit_hold_duration()
            save_input_config()
        elif choice == "5":
            edit_hz_rate()
            save_input_config()
        elif choice == "":
            # Backspace 键在 input() 中无法直接捕获，需要特殊处理
            # 这里简化处理：空输入且用户确认返回
            confirm = input("\n是否返回主程序？(Y/N): ").strip().lower()
            if confirm in ["y", "yes"]:
                print("\n返回主程序...")
                break
        else:
            print("❌ 无效选择，请输入 1-5")


# ==================== 键盘监听和点击 ====================
def get_randomized_position(x, y):
    """获取随机化后的位置"""
    range_str = runtime_config["randomize_range"]
    try:
        parts = range_str.split(",")
        if len(parts) == 2:
            offset_x = int(parts[0])
            offset_y = int(parts[1])
            if offset_x > 0 or offset_y > 0:
                new_x = x + random.randint(-offset_x, offset_x)
                new_y = y + random.randint(-offset_y, offset_y)
                return new_x, new_y
    except:
        pass
    return x, y


def handle_key_press(key_name):
    """处理按键按下，执行触摸点击"""
    global device, key_press_times
    
    if key_name not in key_positions:
        return
    
    x, y = key_positions[key_name]
    
    # 应用随机化
    if runtime_config["randomize_range"] != "0,0":
        x, y = get_randomized_position(x, y)
    
    # 记录按下时间（用于长按检测）
    key_press_times[key_name] = time.time()
    
    # 执行点击
    if device:
        device.input_tap(x, y)
        print(f"✓ 按键 '{key_name}' → 点击 ({x}, {y})")
    else:
        print(f"⚠ 设备未连接，无法点击")


def handle_key_release(key_name):
    """处理按键释放"""
    global key_press_times
    
    if key_name in key_press_times:
        press_duration = time.time() - key_press_times[key_name]
        del key_press_times[key_name]
        
        # 如果需要处理长按释放，可以在这里添加逻辑


def on_key_press(key):
    """键盘按下事件处理"""
    global stop_listener
    
    try:
        # 检查是否按下 '-' 进入设置界面
        if hasattr(key, 'char') and key.char == '-':
            print("\n\n进入设置界面...")
            run_settings()
            print("\n返回主程序，继续监听键盘...")
            print("按键映射列表:")
            for k, pos in key_positions.items():
                print(f"  {k} → ({pos[0]}, {pos[1]})")
            print("-" * 60)
            return True
        
        # 获取按键名称
        if hasattr(key, 'char') and key.char is not None:
            key_name = key.char
        else:
            special_map = {
                keyboard.Key.space: "space",
                keyboard.Key.tab: "tab",
                keyboard.Key.backspace: "backspace",
                keyboard.Key.enter: "enter",
                keyboard.Key.up: "up",
                keyboard.Key.down: "down",
                keyboard.Key.left: "left",
                keyboard.Key.right: "right"
            }
            key_name = special_map.get(key, str(key))
        
        # 退出键（ESC）
        if key == keyboard.Key.esc:
            print("\n⚠ 收到退出信号，程序结束")
            stop_listener = True
            return False
        
        # 处理按键按下
        handle_key_press(key_name)
        
    except Exception as e:
        print(f"键盘处理错误: {e}")
    
    return True


def on_key_release(key):
    """键盘释放事件处理"""
    try:
        if hasattr(key, 'char') and key.char is not None:
            key_name = key.char
        else:
            special_map = {
                keyboard.Key.space: "space",
                keyboard.Key.tab: "tab",
                keyboard.Key.backspace: "backspace",
                keyboard.Key.enter: "enter",
                keyboard.Key.up: "up",
                keyboard.Key.down: "down",
                keyboard.Key.left: "left",
                keyboard.Key.right: "right"
            }
            key_name = special_map.get(key, str(key))
        
        handle_key_release(key_name)
        
    except Exception as e:
        pass
    
    return True


def start_keyboard_listener():
    """启动键盘监听"""
    global stop_listener
    
    print("\n" + "=" * 60)
    print("           键盘监听已启动")
    print("=" * 60)
    print("已加载的按键映射:")
    for key_name, pos in key_positions.items():
        print(f"  {key_name} → ({pos[0]}, {pos[1]})")
    print("\n" + "-" * 60)
    print("控制说明:")
    print("  - 按映射的按键 → 触发 ADB 点击")
    print("  - 按 '-' 键 → 进入设置界面")
    print("  - 按 ESC 键 → 退出程序")
    print("=" * 60)
    print("等待按键输入...\n")
    
    stop_listener = False
    
    with keyboard.Listener(on_press=on_key_press, on_release=on_key_release) as listener:
        while not stop_listener:
            time.sleep(0.1)
            if not listener.running:
                break
        listener.stop()


# ==================== 主函数 ====================
def main():
    """主函数"""
    print("=" * 60)
    print("           主控制程序")
    print("=" * 60)
    
    # 第一步：检查 config.json 完整性
    result = check_config_completeness()
    if not result[0]:
        input("\n按 Enter 键退出...")
        sys.exit(1)
    
    _, config, selected_mode = result
    
    # 第二步：计算按键位置
    global key_positions
    key_positions = calculate_key_positions(config, selected_mode)
    print(f"\n✓ 按键位置计算完成，共 {len(key_positions)} 个按键")
    
    # 第三步：加载 input.json 配置
    if not load_input_config():
        print("⚠ 加载 input.json 失败，使用默认配置")
    else:
        print("✓ 配置加载完成")
    
    # 第四步：连接 USB ADB 设备
    if not connect_usb_adb():
        print("\n❌ 设备连接失败，程序退出")
        input("\n按 Enter 键退出...")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("           初始化完成")
    print("=" * 60)
    print(f"使用模式: {selected_mode}")
    print(f"配置文件: {CONFIG_FILE}")
    print(f"输入配置: {INPUT_FILE}")
    print(f"按键数量: {len(key_positions)}")
    print("=" * 60)
    
    # 第五步：启动键盘监听
    start_keyboard_listener()
    
    print("\n程序已退出")


if __name__ == "__main__":
    main()