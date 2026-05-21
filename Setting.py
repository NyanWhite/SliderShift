import json
import os
from pynput import keyboard

class KeyConfigGenerator:
    def __init__(self):
        self.config_file = os.path.join(os.getcwd(), "config.json")
        self.current_mode = None
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
            }
        }
        self.config_modified = False  # 跟踪配置是否被修改
        
    def check_config_completeness(self):
        """检查配置文件完整度"""
        if not os.path.exists(self.config_file):
            return False, "配置文件不存在"
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
            
            # 检查 32key
            if "32key" in saved_config:
                keys_32 = saved_config["32key"].get("keys", {})
                saved_config["32key"]["completed"] = len(keys_32) == 32
            else:
                saved_config["32key"] = self.config["32key"].copy()
                saved_config["32key"]["completed"] = False
            
            # 检查 16key
            if "16key" in saved_config:
                keys_16 = saved_config["16key"].get("keys", {})
                saved_config["16key"]["completed"] = len(keys_16) >= 1
            else:
                saved_config["16key"] = self.config["16key"].copy()
                saved_config["16key"]["completed"] = False
            
            # 检查 air 模式
            if "air" in saved_config:
                keys_air = saved_config["air"].get("keys", {})
                saved_config["air"]["completed"] = len(keys_air) >= 1
            else:
                saved_config["air"] = self.config["air"].copy()
                saved_config["air"]["completed"] = False
            
            if "active_mode" not in saved_config:
                saved_config["active_mode"] = None
            
            self.config = saved_config
            return True, "配置加载成功"
            
        except Exception as e:
            return False, f"配置文件读取错误: {e}"
    
    def save_config(self):
        """保存完整配置（仅在修改时保存）"""
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
    
    def show_current_status(self):
        """显示当前配置状态"""
        print("\n" + "="*50)
        print("      当前配置状态")
        print("="*50)
        
        if self.config["32key"]["completed"]:
            print(f"✓ 32key模式: 已完成 ({len(self.config['32key']['keys'])}/32个按键)")
            print(f"  - 缩限模式: {'开启' if self.config['32key']['limit'] else '关闭'}")
        else:
            print(f"✗ 32key模式: 未完成 ({len(self.config['32key']['keys'])}/32个按键)")
        
        if self.config["16key"]["completed"]:
            print(f"✓ 16key模式: 已完成 ({len(self.config['16key']['keys'])}个按键)")
            print(f"  - 缩限模式: {'开启' if self.config['16key']['limit'] else '关闭'}")
        else:
            print(f"✗ 16key模式: 未完成 ({len(self.config['16key']['keys'])}个按键)")
        
        if self.config["air"]["completed"]:
            print(f"✓ Air模式: 已完成 ({len(self.config['air']['keys'])}个按键)")
        else:
            print(f"✗ Air模式: 未完成 ({len(self.config['air']['keys'])}个按键)")
        
        if self.config["active_mode"]:
            print(f"\n当前激活模式: {self.config['active_mode']}")
        else:
            print(f"\n当前激活模式: 未选择")
        
        print("="*50)
    
    def select_active_mode(self):
        """选择要使用的模式"""
        while True:
            print("\n" + "="*50)
            print("      选择要使用的模式")
            print("="*50)
            
            if self.config["32key"]["completed"]:
                print("1. 32key模式 (已完成)")
            else:
                print("1. 32key模式 (未完成，需要配置)")
            
            if self.config["16key"]["completed"]:
                print("2. 16key模式 (已完成)")
            else:
                print("2. 16key模式 (未完成，需要配置)")
            
            if self.config["air"]["completed"]:
                print("3. Air模式 (已完成，无按键上限)")
            else:
                print("3. Air模式 (未完成，需要配置，无按键上限)")
            
            print("4. 退出程序")
            print("="*50)
            
            choice = input("请选择 (1/2/3/4): ").strip()
            
            if choice == "1" and self.config["32key"]["completed"]:
                if self.config["active_mode"] != "32key":
                    self.config["active_mode"] = "32key"
                    self.config_modified = True
                    self.save_config()
                print(f"\n✓ 已切换到 32key 模式")
                return "32key"
            elif choice == "2" and self.config["16key"]["completed"]:
                if self.config["active_mode"] != "16key":
                    self.config["active_mode"] = "16key"
                    self.config_modified = True
                    self.save_config()
                print(f"\n✓ 已切换到 16key 模式")
                return "16key"
            elif choice == "3" and self.config["air"]["completed"]:
                if self.config["active_mode"] != "air":
                    self.config["active_mode"] = "air"
                    self.config_modified = True
                    self.save_config()
                print(f"\n✓ 已切换到 Air 模式")
                return "air"
            elif choice == "1" and not self.config["32key"]["completed"]:
                print("\n❌ 32key模式未完成，请先配置")
                input("按 Enter 继续...")
                return self.configure_incomplete_mode("32key")
            elif choice == "2" and not self.config["16key"]["completed"]:
                print("\n❌ 16key模式未完成，请先配置")
                input("按 Enter 继续...")
                return self.configure_incomplete_mode("16key")
            elif choice == "3" and not self.config["air"]["completed"]:
                print("\n❌ Air模式未完成，请先配置")
                input("按 Enter 继续...")
                return self.configure_incomplete_mode("air")
            elif choice == "4":
                return None
            else:
                print("❌ 无效选择")
    
    def configure_incomplete_mode(self, mode):
        """配置未完成的模式"""
        print(f"\n开始配置 {mode} 模式...")
        
        # 只有 32key 和 16key 需要设置缩限模式，air 不需要
        if mode != "air":
            while True:
                print("\n" + "="*40)
                print(f"      {mode}模式 - 缩限模式设置")
                print("="*40)
                print("缩限模式开启后，将限制按键的输入范围")
                print("1. 开启缩限模式 (true)")
                print("2. 关闭缩限模式 (false)")
                print("="*40)
                
                choice = input("请选择 (1/2): ").strip()
                
                if choice == "1":
                    if self.config[mode]["limit"] != True:
                        self.config[mode]["limit"] = True
                        self.config_modified = True
                    print("✓ 已开启缩限模式")
                    break
                elif choice == "2":
                    if self.config[mode]["limit"] != False:
                        self.config[mode]["limit"] = False
                        self.config_modified = True
                    print("✓ 已关闭缩限模式")
                    break
                else:
                    print("❌ 无效选择，请输入 1 或 2")
        
        # 配置按键
        if mode == "32key":
            self.run_32key_config()
        elif mode == "16key":
            self.run_16key_config()
        else:  # air 模式
            self.run_air_config()
        
        self.config[mode]["completed"] = True
        self.config["active_mode"] = mode
        self.config_modified = True
        self.save_config()
        
        return mode
    
    def modify_existing_mode(self, mode):
        """修改已完成的模式配置"""
        print(f"\n开始修改 {mode} 模式配置...")
        
        print("\n当前按键映射:")
        keys = self.config[mode]["keys"]
        for idx, key in keys.items():
            print(f"  按键 {idx:3s} → {key}")
        
        modify = input("\n是否重新配置按键映射？(y/n): ").strip().lower()
        
        if modify == 'y':
            # 重新配置按键映射
            self.config[mode]["keys"] = {}
            self.config[mode]["completed"] = False
            
            # 只有 32key 和 16key 需要重新配置缩限模式，air 不需要
            if mode != "air":
                while True:
                    print("\n" + "="*40)
                    print(f"      {mode}模式 - 缩限模式设置")
                    print("="*40)
                    print("缩限模式开启后，将限制按键的输入范围")
                    print(f"当前: {'开启' if self.config[mode]['limit'] else '关闭'}")
                    print("1. 开启缩限模式 (true)")
                    print("2. 关闭缩限模式 (false)")
                    print("3. 保持不变")
                    print("="*40)
                    
                    choice = input("请选择 (1/2/3): ").strip()
                    
                    if choice == "1":
                        if self.config[mode]["limit"] != True:
                            self.config[mode]["limit"] = True
                            self.config_modified = True
                        break
                    elif choice == "2":
                        if self.config[mode]["limit"] != False:
                            self.config[mode]["limit"] = False
                            self.config_modified = True
                        break
                    elif choice == "3":
                        break
                    else:
                        print("❌ 无效选择")
            
            # 重新配置按键
            if mode == "32key":
                self.run_32key_config()
            elif mode == "16key":
                self.run_16key_config()
            else:
                self.run_air_config()
            
            self.config[mode]["completed"] = True
            self.config["active_mode"] = mode
            self.config_modified = True
            self.save_config()
            print(f"\n✓ {mode} 模式配置已更新")
        
        else:
            # 不重新配置按键映射，只修改缩限模式（air 模式跳过此步骤）
            if mode == "air":
                print("\nAir 模式无需修改缩限模式，配置保持不变")
                return mode
            
            print("\n保持当前按键映射，只修改缩限模式设置")
            
            while True:
                print("\n" + "="*40)
                print(f"      {mode}模式 - 缩限模式设置")
                print("="*40)
                print("缩限模式开启后，将限制按键的输入范围")
                print(f"当前: {'开启' if self.config[mode]['limit'] else '关闭'}")
                print("1. 开启缩限模式 (true)")
                print("2. 关闭缩限模式 (false)")
                print("3. 保持不变并返回")
                print("="*40)
                
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
                    print("保持不变，返回主界面")
                    break
                else:
                    print("❌ 无效选择")
            
            # 如果有修改，保存配置
            if self.config_modified:
                self.save_config()
            else:
                print("\n未检测到任何修改，配置文件保持不变")
        
        return mode
    
    def is_valid_key(self, key):
        """判断是否为需要记录的按键（过滤功能键）"""
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
        """获取按键的友好名称"""
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
        """32key配置流程（带重复检测）"""
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
            
            # 检查重复
            if key_name in current_keys:
                print(f"\r⚠ 按键 '{key_name}' 已存在！请按其他键 ({len(current_keys)}/32)", end="")
                return True
            
            # 添加新按键
            current_keys.append(key_name)
            print(f"\r✓ 已录入: {len(current_keys)}/32 个按键 - 最新按键: {key_name}", end="")
            
            if len(current_keys) >= 32:
                print("\n\n✓ 已达到32个按键，自动完成录入")
                return False
            
            return True
        
        while True:
            current_keys = []
            print(f"\n\n开始录入32个按键...")
            print(f"  - Enter键: 保存当前录入并结束")
            print(f"  - Backspace键: 清空所有已录入按键，重新开始")
            print(f"  - 功能键(F1-Esc等)将被自动过滤")
            print(f"  - 重复按键将被自动忽略")
            print("-" * 50)
            
            with keyboard.Listener(on_press=on_press) as listener:
                listener.join()
            
            if len(current_keys) < 32:
                print(f"\n❌ 按键不足32个！当前只有 {len(current_keys)} 个，还需录入 {32 - len(current_keys)} 个")
                print("按 Backspace 键重新录入，或按 Enter 键强制保存")
                
                def on_decision(key):
                    if key == keyboard.Key.backspace:
                        self.decision = "restart"
                        return False
                    elif key == keyboard.Key.enter:
                        self.decision = "save"
                        return False
                    return True
                
                self.decision = None
                with keyboard.Listener(on_press=on_decision) as listener:
                    listener.join()
                
                if self.decision == "restart":
                    continue
                elif self.decision == "save":
                    if len(current_keys) == 0:
                        print("\n❌ 无法保存空配置，请重新录入")
                        continue
            elif len(current_keys) > 32:
                current_keys = current_keys[:32]
                print(f"\n⚠ 已超过32个按键，只保留前32个")
            
            # 确认保存
            print("\n" + "="*50)
            print("按键对应关系如下：")
            print("="*50)
            for idx, key in enumerate(current_keys[:32], 1):
                print(f"  按键 {idx:2d} → {key}")
            print("="*50)
            
            print("\n按 Enter 确认保存，按 Backspace 重新录入")
            
            def on_confirm(key):
                if key == keyboard.Key.enter:
                    self.confirm_result = True
                    return False
                elif key == keyboard.Key.backspace:
                    self.confirm_result = False
                    return False
                return True
            
            self.confirm_result = None
            with keyboard.Listener(on_press=on_confirm) as listener:
                listener.join()
            
            if self.confirm_result:
                final_keys = current_keys[:32]
                while len(final_keys) < 32:
                    final_keys.append(None)
                self.config["32key"]["keys"] = {str(i+1): final_keys[i] for i in range(32) if final_keys[i] is not None}
                self.config_modified = True
                break
            else:
                print("重新开始录入...")
                continue
    
    def run_16key_config(self):
        """16key配置流程（带重复检测）"""
        current_keys = []
        
        def on_press(key):
            nonlocal current_keys
            
            if key == keyboard.Key.enter:
                print("\n\n✓ 按Enter键，准备保存配置...")
                return False
                
            if key == keyboard.Key.backspace:
                print("\n\n⚠ 按Backspace键，清空重新录入...")
                current_keys = []
                print("已清空，重新开始录入")
                return True
                
            if not self.is_valid_key(key):
                return True
            
            key_name = self.get_key_name(key)
            
            # 检查重复
            if key_name in current_keys:
                print(f"\r⚠ 按键 '{key_name}' 已存在！请按其他键 (已录入 {len(current_keys)} 个)", end="")
                return True
            
            # 添加新按键
            current_keys.append(key_name)
            print(f"\r✓ 已录入: {len(current_keys)} 个按键 - 最新按键: {key_name}", end="")
            
            return True
        
        while True:
            current_keys = []
            print(f"\n\n开始录入按键（至少1个）...")
            print(f"  - Enter键: 保存当前录入并结束")
            print(f"  - Backspace键: 清空所有已录入按键，重新开始")
            print(f"  - 功能键(F1-Esc等)将被自动过滤")
            print(f"  - 重复按键将被自动忽略")
            print("-" * 50)
            
            with keyboard.Listener(on_press=on_press) as listener:
                listener.join()
            
            if len(current_keys) == 0:
                print(f"\n❌ 至少需要录入1个按键！")
                print("按 Backspace 键重新录入")
                
                def on_backspace(key):
                    if key == keyboard.Key.backspace:
                        self.backspace_pressed = True
                        return False
                    return True
                
                self.backspace_pressed = False
                with keyboard.Listener(on_press=on_backspace) as listener:
                    listener.join()
                
                if self.backspace_pressed:
                    continue
            
            # 确认保存
            print("\n" + "="*50)
            print("按键对应关系如下：")
            print("="*50)
            for idx, key in enumerate(current_keys, 1):
                print(f"  按键 {idx:2d} → {key}")
            print("="*50)
            
            print("\n按 Enter 确认保存，按 Backspace 重新录入")
            
            def on_confirm(key):
                if key == keyboard.Key.enter:
                    self.confirm_result = True
                    return False
                elif key == keyboard.Key.backspace:
                    self.confirm_result = False
                    return False
                return True
            
            self.confirm_result = None
            with keyboard.Listener(on_press=on_confirm) as listener:
                listener.join()
            
            if self.confirm_result:
                self.config["16key"]["keys"] = {str(i+1): current_keys[i] for i in range(len(current_keys))}
                self.config_modified = True
                break
            else:
                print("重新开始录入...")
                continue
    
    def run_air_config(self):
        """Air模式配置流程（无上限，至少1个，带重复检测，无缩限模式）"""
        current_keys = []
        
        def on_press(key):
            nonlocal current_keys
            
            if key == keyboard.Key.enter:
                print("\n\n✓ 按Enter键，准备保存配置...")
                return False
                
            if key == keyboard.Key.backspace:
                print("\n\n⚠ 按Backspace键，清空重新录入...")
                current_keys = []
                print("已清空，重新开始录入")
                return True
                
            if not self.is_valid_key(key):
                return True
            
            key_name = self.get_key_name(key)
            
            # 检查重复
            if key_name in current_keys:
                print(f"\r⚠ 按键 '{key_name}' 已存在！请按其他键 (已录入 {len(current_keys)} 个)", end="")
                return True
            
            # 添加新按键
            current_keys.append(key_name)
            print(f"\r✓ 已录入: {len(current_keys)} 个按键 - 最新按键: {key_name} (无上限，按Enter结束)", end="")
            
            return True
        
        while True:
            current_keys = []
            print(f"\n\n开始录入Air模式按键（无上限，至少1个）...")
            print(f"  - Enter键: 保存当前录入并结束")
            print(f"  - Backspace键: 清空所有已录入按键，重新开始")
            print(f"  - 功能键(F1-Esc等)将被自动过滤")
            print(f"  - 重复按键将被自动忽略")
            print(f"  - 可以录入任意数量的按键，按Enter结束")
            print("-" * 50)
            
            with keyboard.Listener(on_press=on_press) as listener:
                listener.join()
            
            if len(current_keys) == 0:
                print(f"\n❌ 至少需要录入1个按键！")
                print("按 Backspace 键重新录入，或按 Enter 键退出")
                
                def on_decision(key):
                    if key == keyboard.Key.backspace:
                        self.decision = "restart"
                        return False
                    elif key == keyboard.Key.enter:
                        self.decision = "exit"
                        return False
                    return True
                
                self.decision = None
                with keyboard.Listener(on_press=on_decision) as listener:
                    listener.join()
                
                if self.decision == "restart":
                    continue
                elif self.decision == "exit":
                    print("\n退出 Air 模式配置")
                    return
            
            # 确认保存
            print("\n" + "="*50)
            print("Air模式按键对应关系如下：")
            print("="*50)
            for idx, key in enumerate(current_keys, 1):
                print(f"  按键 {idx:2d} → {key}")
            print(f"\n总计: {len(current_keys)} 个按键")
            print("="*50)
            
            print("\n按 Enter 确认保存，按 Backspace 重新录入")
            
            def on_confirm(key):
                if key == keyboard.Key.enter:
                    self.confirm_result = True
                    return False
                elif key == keyboard.Key.backspace:
                    self.confirm_result = False
                    return False
                return True
            
            self.confirm_result = None
            with keyboard.Listener(on_press=on_confirm) as listener:
                listener.join()
            
            if self.confirm_result:
                self.config["air"]["keys"] = {str(i+1): current_keys[i] for i in range(len(current_keys))}
                self.config_modified = True
                break
            else:
                print("重新开始录入...")
                continue
    
    def run(self):
        """主运行流程"""
        print("正在初始化...")
        print(f"配置文件路径: {self.config_file}")
        
        is_valid, message = self.check_config_completeness()
        
        if is_valid:
            print(f"\n✓ {message}")
            self.show_current_status()
            
            modify = input("\n是否修改配置？(y/n): ").strip().lower()
            if modify == 'y':
                print("\n选择要修改的模式：")
                print("1. 32key模式")
                print("2. 16key模式")
                print("3. Air模式")
                choice = input("请选择 (1/2/3): ").strip()
                
                if choice == "1":
                    self.modify_existing_mode("32key")
                elif choice == "2":
                    self.modify_existing_mode("16key")
                elif choice == "3":
                    self.modify_existing_mode("air")
        else:
            print(f"\n⚠ {message}")
            print("需要配置至少一个模式")
        
        # 选择激活模式（会再次显示状态）
        active_mode = self.select_active_mode()
        if active_mode:
            print(f"\n✓ 程序已就绪，当前使用 {active_mode} 模式")
            print(f"✓ 配置文件已保存至: {self.config_file}")
        else:
            print("\n程序退出")


def main():
    try:
        generator = KeyConfigGenerator()
        generator.run()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()