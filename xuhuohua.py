# 抖音自动续火花工具
# 自动发送抖音私信给指定联系人，保持互动关系不断
#
# 使用前请先安装依赖：
# pip install selenium webdriver-manager schedule pyautogui
#
# 如果是Mac系统，还需要安装：
# pip install python3-xlib
# brew install python-tk python-imaging

import time
import schedule
import os
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import pyautogui
import pickle
import requests
from datetime import datetime, date
from typing import Dict, Any

# 用户配置文件路径
USER_CONFIG_PATH = "xuhuohua_users.json"

# 多用户配置 - 可以添加多个用户
# 每个用户需要设置: 
# - name: 用户名称(用于区分不同用户)
# - contacts: 联系人列表
# - message: 要发送的消息
# - cookie_path: cookie保存路径
# - icon_position: 私信按钮的坐标位置
USERS = [
    {
        "name": "示例用户",  # 用户名称
        "contacts": ["联系人1", "联系人2"],  # 联系人列表
        "message": "[自动程序发送]续火花咯！",  # 消息内容
        "cookie_path": "douyin_cookies.txt",  # cookie保存路径
        "icon_position": {'x': 1600, 'y': 170}  # 私信按钮坐标 (根据屏幕分辨率调整)
    },
    # 可以添加更多用户配置
    # {
    #     "name": "用户2",
    #     "contacts": ["联系人1", "联系人2"],
    #     "message": "自定义消息",
    #     "cookie_path": "douyin_cookies_user2.txt",
    #     "icon_position": {'x': 1600, 'y': 170}
    # },
]

# 当前活跃用户索引
ACTIVE_USER_INDEX = 0  # 0表示使用USERS列表中的第一个用户

def cdp_insert_text(driver, text: str):
    # 用 CDP 把整段文本插入到当前焦点处（支持所有 emoji）
    driver.execute_cdp_cmd("Input.insertText", {"text": text})

def cdp_press_enter(driver):
    # 用 CDP 发送一次回车
    driver.execute_cdp_cmd("Input.dispatchKeyEvent", {
        "type": "keyDown", "key": "Enter", "code": "Enter",
        "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13
    })
    driver.execute_cdp_cmd("Input.dispatchKeyEvent", {
        "type": "keyUp", "key": "Enter", "code": "Enter",
        "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13
    })
def sanitize_to_bmp(s: str) -> str:
    return "".join(ch for ch in s if ord(ch) <= 0xFFFF)


def save_user_config():
    """保存用户配置到文件"""
    try:
        config = {
            "users": USERS,
            "active_user_index": ACTIVE_USER_INDEX
        }
        
        # 确保icon_position能够正确序列化
        for user in config["users"]:
            if "icon_position" in user and not isinstance(user["icon_position"], dict):
                user["icon_position"] = {"x": user["icon_position"].get("x", 1600), 
                                        "y": user["icon_position"].get("y", 170)}
        
        with open(USER_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        
        print(f"用户配置已保存到 {USER_CONFIG_PATH}")
        return True
    except Exception as e:
        print(f"保存用户配置失败: {e}")
        return False

def load_user_config():
    """从文件加载用户配置"""
    global USERS, ACTIVE_USER_INDEX
    
    try:
        if not os.path.exists(USER_CONFIG_PATH):
            print(f"用户配置文件不存在，将使用默认配置")
            return False
            
        with open(USER_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        if "users" in config and isinstance(config["users"], list) and len(config["users"]) > 0:
            USERS = config["users"]
            if "active_user_index" in config and isinstance(config["active_user_index"], int):
                if 0 <= config["active_user_index"] < len(USERS):
                    ACTIVE_USER_INDEX = config["active_user_index"]
                else:
                    ACTIVE_USER_INDEX = 0
            
            print(f"成功加载了 {len(USERS)} 个用户配置")
            return True
        else:
            print("用户配置文件格式错误，将使用默认配置")
            return False
    except Exception as e:
        print(f"加载用户配置失败: {e}")
        return False

def get_active_user():
    """获取当前活跃用户的配置"""
    if 0 <= ACTIVE_USER_INDEX < len(USERS):
        return USERS[ACTIVE_USER_INDEX]
    else:
        raise ValueError("无效的用户索引")

def save_cookies(driver, path):
    """保存cookies到文件"""
    cookies_dir = os.path.dirname(path)
    if cookies_dir and not os.path.exists(cookies_dir):
        os.makedirs(cookies_dir)
        
    with open(path, "wb") as f:
        pickle.dump(driver.get_cookies(), f)

def load_cookies(driver, path):
    """从文件加载cookies"""
    try:
        if not os.path.exists(path):
            print(f"Cookie文件不存在: {path}")
            return False
            
        with open(path, "rb") as f:
            try:
                cookies = pickle.load(f)
                if not cookies:  # 检查cookies是否为空
                    print(f"Cookie文件存在但内容为空: {path}")
                    return False
                    
                for cookie in cookies:
                    try:
                        # 过滤掉无效的cookie属性，避免错误
                        if 'expiry' in cookie and isinstance(cookie['expiry'], float):
                            cookie['expiry'] = int(cookie['expiry'])
                        driver.add_cookie(cookie)
                    except Exception as e:
                        print(f"添加单个cookie时出错: {e}")
                        # 继续添加其他cookie
                return True
            except Exception as e:
                print(f"读取cookie文件出错: {e}")
                return False
    except Exception as e:
        print(f"加载cookie过程中出现异常: {e}")
        return False

def login_and_save_cookies(driver, cookie_path):
    """引导用户登录并保存cookies"""
    driver.get("https://www.douyin.com/")
    print(f"请手动扫码登录并等待页面加载…（30秒后将自动保存cookie到 {cookie_path}）")
    time.sleep(30)
    save_cookies(driver, cookie_path)
    print("Cookie保存成功，可用于下次自动登录")

def take_screenshots(driver, name, user_name=None):
    """保存当前页面截图，便于调试"""
    try:
        if user_name:
            # 如果提供了用户名，则保存到用户专属文件夹
            directory = f"screenshots/{user_name}"
            if not os.path.exists(directory):
                os.makedirs(directory)
            screenshot_path = f"{directory}/douyin_{name}.png"
        else:
            # 否则保存到默认位置
            screenshot_path = f"douyin_{name}.png"
            
        driver.save_screenshot(screenshot_path)
        print(f"已保存截图: {screenshot_path}")
    except Exception as e:
        print(f"保存截图失败: {e}")

def init_driver(user_config):
    """初始化浏览器并使用用户配置登录"""
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--start-maximized")
    
    try:
        print(f"正在为用户 [{user_config['name']}] 初始化Chrome浏览器...")
        driver_path = ChromeDriverManager().install()
        service = webdriver.chrome.service.Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print("Chrome浏览器初始化成功")
    except Exception as e:
        print(f"Chrome浏览器初始化失败: {e}")
        raise

    try:
        print("正在访问抖音网站...")
        driver.get("https://www.douyin.com/")
        print("成功加载抖音网站")
        time.sleep(2)
        
        cookie_path = user_config["cookie_path"]
        try:
            print(f"尝试从 {cookie_path} 加载cookie...")
            if load_cookies(driver, cookie_path):
                driver.refresh()
                print("已自动载入cookie尝试自动登录douyin...")
                time.sleep(3)
            else:
                print(f"未找到cookie文件: {cookie_path}")
                login_and_save_cookies(driver, cookie_path)
        except Exception as e:
            print(f"自动载入cookie失败: {e}")
            login_and_save_cookies(driver, cookie_path)
            
        return driver
    except Exception as e:
        print(f"访问抖音网站失败: {e}")
        driver.quit()
        raise

def send_message_to_contact(driver, contact_name, message, user_config):
    """为指定联系人发送消息"""
    user_name = user_config["name"]
    icon_position = user_config["icon_position"]
    
    try:
        # 访问抖音首页
        driver.get("https://www.douyin.com/")
        time.sleep(5)
        take_screenshots(driver, "home", user_name)
        
        # 点击私信按钮
        try:
            print(f"点击私信按钮: ({icon_position['x']}, {icon_position['y']})")
            
            # 获取浏览器窗口位置
            window_rect = driver.get_window_rect()
            window_x = window_rect['x']
            window_y = window_rect['y']
            
            # 计算屏幕绝对坐标
            screen_x = window_x + icon_position['x']
            screen_y = window_y + icon_position['y']
            
            # 移动鼠标并点击
            pyautogui.moveTo(screen_x, screen_y, duration=0.5)
            pyautogui.click()
            
            print("已点击私信按钮")
            time.sleep(3)
            take_screenshots(driver, "after_click_message_icon", user_name)
        except Exception as e:
            print(f"点击私信按钮失败: {e}")
            return False
        
        # 查找联系人
        print(f"查找联系人: {contact_name}")
        time.sleep(2)
        
        # 联系人选择器
        contact_selectors = [
            f"//div[contains(text(), '{contact_name}')]",
            f"//span[contains(text(), '{contact_name}')]",
            f"//div[contains(., '{contact_name}')]"
        ]
        
        contact_element = None
        for selector in contact_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        print(f"找到联系人: {contact_name}")
                        contact_element = element
                        break
                if contact_element:
                    break
            except:
                continue
        
        if not contact_element:
            print(f"未找到联系人: {contact_name}")
            return False
        
        # 点击联系人
        try:
            print(f"点击联系人")
            driver.execute_script("arguments[0].click();", contact_element)
            time.sleep(3)
            take_screenshots(driver, "after_click_contact", user_name)
        except Exception as e:
            print(f"点击联系人失败: {e}")
            return False
        
        # 查找输入框
        input_element = None
        input_selectors = [
            "//textarea",
            "//div[@contenteditable='true']"
        ]
        
        for selector in input_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        input_element = element
                        print("找到输入框")
                        break
                if input_element:
                    break
            except:
                continue
        
        if not input_element:
            print("未找到输入框")
            return False
        # 输入消息（用 CDP，避免 send_keys 的 BMP 限制）
        try:
            # 确保输入框在视口且获得焦点
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_element)
            input_element.click()
            time.sleep(0.3)

            # 如果是 contenteditable，清空旧内容（防止残留）
            try:
                tag = input_element.tag_name.lower()
                is_ce = input_element.get_attribute("contenteditable") == "true"
                if is_ce:
                    driver.execute_script("arguments[0].innerHTML='';", input_element)
                else:
                    input_element.clear()
            except:
                pass

            # 用 CDP 注入消息
            cdp_insert_text(driver, message)
            time.sleep(0.4)
            print(f"已输入消息(CDP): {message}")
            take_screenshots(driver, "after_input_message", user_name)
        except Exception as e:
            print(f"输入消息失败(CDP): {e}")
            # 兜底：去掉非BMP后用 send_keys（不推荐，但保证不崩）
            try:
                safe_msg = sanitize_to_bmp(message)
                input_element.clear()
                input_element.send_keys(safe_msg)
                time.sleep(0.4)
                print(f"已输入消息(降级 BMP): {safe_msg}")
            except Exception as e2:
                print(f"输入消息降级失败: {e2}")
                return False

        # 发送消息（优先用 CDP 回车）
        try:
            input_element.click()
            time.sleep(0.2)
            cdp_press_enter(driver)
            time.sleep(0.6)
            take_screenshots(driver, "after_send", user_name)
            print(f"成功发送消息: {message}")
            return True
        except Exception as e:
            print(f"发送消息失败(CDP): {e}")
            # 兜底方案：pyautogui 回车
            try:
                pyautogui.press('enter')
                time.sleep(0.6)
                print("成功发送消息(pyautogui)")
                return True
            except:
                print("所有发送方式均失败")
                return False
            
    except Exception as e:
        print(f"发送消息失败: {e}")
        return False

def send_messages_for_user(user_config):
    """为指定用户发送所有消息"""
    try:
        user_name = user_config["name"]
        contacts = user_config["contacts"]
        message = build_todays_message_for_city("西安", "CN")
        
        print(f"开始为用户 [{user_name}] 发送消息...")
        driver = init_driver(user_config)
        
        success_count = 0
        for contact in contacts:
            print(f"向 {contact} 发送消息...")
            result = send_message_to_contact(driver, contact, message, user_config)
            if result:
                print(f"向 {contact} 发送消息成功")
                success_count += 1
            else:
                print(f"向 {contact} 发送消息失败")
            time.sleep(3)
        
        driver.quit()
        print(f"用户 [{user_name}] 消息发送完毕！成功: {success_count}/{len(contacts)}")
        return success_count > 0
        
    except Exception as e:
        print(f"发送消息过程中发生错误: {e}")
        try:
            driver.quit()
        except:
            pass
        return False

def send_messages_for_all_users():
    """为所有配置的用户执行续火花操作"""
    print("\n" + "="*50)
    print(f"开始为所有用户执行续火花操作 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    total_users = len(USERS)
    success_users = 0
    
    for i, user in enumerate(USERS):
        user_name = user["name"]
        print(f"\n[{i+1}/{total_users}] 正在为用户 [{user_name}] 执行续火花操作...")
        
        try:
            result = send_messages_for_user(user)
            if result:
                success_users += 1
                print(f"用户 [{user_name}] 续火花操作成功")
            else:
                print(f"用户 [{user_name}] 续火花操作失败")
        except Exception as e:
            print(f"用户 [{user_name}] 执行过程中出错: {e}")
        
        # 如果不是最后一个用户，等待一段时间再执行下一个用户
        if i < total_users - 1:
            wait_time = 30  # 用户之间的等待时间，单位秒
            print(f"等待 {wait_time} 秒后执行下一个用户...")
            time.sleep(wait_time)
    
    print("\n" + "="*50)
    print(f"所有用户续火花操作完成: 成功 {success_users}/{total_users}")
    print(f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    return success_users > 0

def send_messages_daily():
    """每日发送消息的定时任务，现在会为所有用户发送消息"""
    return send_messages_for_all_users()

def switch_user(user_index):
    """切换活跃用户"""
    global ACTIVE_USER_INDEX
    if 0 <= user_index < len(USERS):
        ACTIVE_USER_INDEX = user_index
        print(f"已切换到用户: {USERS[user_index]['name']}")
        # 自动保存用户配置
        save_user_config()
        return True
    else:
        print(f"无效的用户索引: {user_index}，用户索引应在0到{len(USERS)-1}之间")
        return False

def list_users():
    """列出所有配置的用户"""
    print("\n已配置的用户列表:")
    for i, user in enumerate(USERS):
        active = " [当前活跃]" if i == ACTIVE_USER_INDEX else ""
        print(f"{i}. {user['name']}{active}")
        print(f"   联系人: {', '.join(user['contacts'])}")
        print(f"   消息: {user['message']}")
        print(f"   Cookie路径: {user['cookie_path']}")
        print()

def add_user(name, contacts, message, cookie_path=None, icon_position=None):
    """添加新用户"""
    if cookie_path is None:
        cookie_path = f"douyin_cookies_{name}.txt"
    
    if icon_position is None and len(USERS) > 0:
        # 默认使用第一个用户的图标位置
        icon_position = USERS[0]["icon_position"]
    elif icon_position is None:
        icon_position = {'x': 1600, 'y': 170}
        
    new_user = {
        "name": name,
        "contacts": contacts,
        "message": message,
        "cookie_path": cookie_path,
        "icon_position": icon_position
    }
    
    USERS.append(new_user)
    print(f"已添加新用户: {name}")
    # 自动保存用户配置
    save_user_config()
    return len(USERS) - 1  # 返回新用户的索引

def delete_user(user_index):
    """删除指定用户"""
    global ACTIVE_USER_INDEX
    
    if 0 <= user_index < len(USERS):
        user_name = USERS[user_index]["name"]
        USERS.pop(user_index)
        
        # 如果删除的是当前活跃用户，调整活跃用户索引
        if user_index == ACTIVE_USER_INDEX:
            ACTIVE_USER_INDEX = 0 if len(USERS) > 0 else -1
        elif user_index < ACTIVE_USER_INDEX:
            ACTIVE_USER_INDEX -= 1
            
        print(f"已删除用户: {user_name}")
        # 自动保存用户配置
        save_user_config()
        return True
    else:
        print(f"无效的用户索引: {user_index}")
        return False

def edit_user(user_index):
    """编辑指定用户的信息"""
    if 0 <= user_index < len(USERS):
        user = USERS[user_index]
        print(f"\n正在编辑用户 [{user['name']}] 的信息:")
        
        # 编辑用户名
        new_name = input(f"用户名 [{user['name']}] (直接回车保持不变): ")
        if new_name.strip():
            user["name"] = new_name.strip()
            
        # 编辑联系人
        old_contacts = ', '.join(user["contacts"])
        new_contacts = input(f"联系人 [{old_contacts}] (直接回车保持不变): ")
        if new_contacts.strip():
            user["contacts"] = [c.strip() for c in new_contacts.split(",")]
            
        # 编辑消息
        new_message = input(f"消息 [{user['message']}] (直接回车保持不变): ")
        if new_message.strip():
            user["message"] = new_message.strip()
            
        # 编辑私信按钮坐标
        x = user["icon_position"]["x"]
        y = user["icon_position"]["y"]
        new_x = input(f"私信按钮X坐标 [{x}] (直接回车保持不变): ")
        if new_x.strip():
            try:
                user["icon_position"]["x"] = int(new_x.strip())
            except:
                print("X坐标必须是数字，保持原值不变")
                
        new_y = input(f"私信按钮Y坐标 [{y}] (直接回车保持不变): ")
        if new_y.strip():
            try:
                user["icon_position"]["y"] = int(new_y.strip())
            except:
                print("Y坐标必须是数字，保持原值不变")
                
        print(f"用户 [{user['name']}] 信息已更新")
        # 自动保存用户配置
        save_user_config()
        return True
    else:
        print(f"无效的用户索引: {user_index}")
        return False

def setup_new_user():
    """交互式设置新用户"""
    name = input("请输入用户名称: ")
    contacts_str = input("请输入联系人列表(用逗号分隔): ")
    contacts = [c.strip() for c in contacts_str.split(",")]
    message = input("请输入要发送的消息: ")
    
    user_index = add_user(name, contacts, message)
    
    if input("是否立即为该用户登录并保存cookie? (y/n): ").lower() == 'y':
        switch_user(user_index)
        user_config = USERS[user_index]
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
        login_and_save_cookies(driver, user_config["cookie_path"])
        driver.quit()
    
    return user_index

def refresh_user_cookies(user_index):
    """为指定用户刷新cookie"""
    if 0 <= user_index < len(USERS):
        user_config = USERS[user_index]
        user_name = user_config["name"]
        cookie_path = user_config["cookie_path"]
        
        print(f"\n开始为用户 [{user_name}] 刷新cookie...")
        try:
            # 初始化临时浏览器
            chrome_options = Options()
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--start-maximized")
            
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
            print(f"临时浏览器已启动，准备刷新cookie")
            
            # 引导用户登录
            login_and_save_cookies(driver, cookie_path)
            
            # 验证是否成功登录
            driver.get("https://www.douyin.com/")
            time.sleep(3)
            
            # 检查是否有登录状态的元素
            try:
                # 尝试寻找个人头像等登录状态的标志
                profile_elements = driver.find_elements(By.XPATH, "//div[contains(@class, 'avatar') or contains(@class, 'profile')]")
                if profile_elements and any(e.is_displayed() for e in profile_elements):
                    print(f"cookie刷新成功！用户 [{user_name}] 已成功登录")
                else:
                    print(f"警告: 可能没有正确登录，请检查 {cookie_path} 是否有效")
            except:
                print(f"无法验证登录状态，但cookie已保存到 {cookie_path}")
            
            driver.quit()
            return True
        except Exception as e:
            print(f"刷新cookie过程中出错: {e}")
            try:
                driver.quit()
            except:
                pass
            return False
    else:
        print(f"无效的用户索引: {user_index}")
        return False

def refresh_active_user_cookies():
    """刷新当前活跃用户的cookie"""
    return refresh_user_cookies(ACTIVE_USER_INDEX)

def send_messages_with_repeat(user_config, repeat_count=1, interval_seconds=10):
    """指定次数重复执行续火花操作
    
    Args:
        user_config: 用户配置
        repeat_count: 重复执行次数
        interval_seconds: 每次执行间隔的秒数
    """
    user_name = user_config["name"]
    
    print(f"为用户 [{user_name}] 开始执行 {repeat_count} 次续火花操作...")
    
    success_count = 0
    for i in range(repeat_count):
        print(f"\n=== 执行第 {i+1}/{repeat_count} 次续火花 ===")
        
        try:
            driver = init_driver(user_config)
            result = False
            
            for contact in user_config["contacts"]:
                print(f"向 {contact} 发送消息...")
                result = send_message_to_contact(driver, contact, user_config["message"], user_config)
                if result:
                    print(f"向 {contact} 发送消息成功")
                    success_count += 1
                else:
                    print(f"向 {contact} 发送消息失败")
                time.sleep(3)
            
            driver.quit()
            
            # 如果不是最后一次执行，则等待指定的间隔时间
            if i < repeat_count - 1:
                print(f"等待 {interval_seconds} 秒后执行下一次...")
                time.sleep(interval_seconds)
                
        except Exception as e:
            print(f"第 {i+1} 次执行时出错: {e}")
            try:
                driver.quit()
            except:
                pass
    
    print(f"\n所有操作完成！用户 [{user_name}] 共执行了 {repeat_count} 次续火花操作，总成功次数: {success_count}")
    return success_count > 0

# —— 基础：WMO 天气代码 -> 中文描述 + Emoji
WMO_MAP = {
    0: ("晴", "☀️"),
    1: ("多云间晴", "🌤️"),
    2: ("多云", "⛅"),
    3: ("阴", "☁️"),
    45: ("雾", "🌫️"), 48: ("雾凇雾", "🌫️"),
    51: ("毛毛雨(小)", "🌦️"), 53: ("毛毛雨(中)", "🌦️"), 55: ("毛毛雨(大)", "🌦️"),
    56: ("冻毛毛雨(小)", "🌧️"), 57: ("冻毛毛雨(大)", "🌧️"),
    61: ("小雨", "🌧️"), 63: ("中雨", "🌧️"), 65: ("大雨", "🌧️"),
    66: ("冻雨(小)", "🌧️"), 67: ("冻雨(大)", "🌧️"),
    71: ("小雪", "🌨️"), 73: ("中雪", "🌨️"), 75: ("大雪", "🌨️"),
    77: ("冰粒", "🌨️"),
    80: ("阵雨(小)", "🌦️"), 81: ("阵雨(中)", "🌦️"), 82: ("阵雨(大)", "🌧️"),
    85: ("阵雪(小)", "🌨️"), 86: ("阵雪(大)", "🌨️"),
    95: ("雷暴", "⛈️"), 96: ("雷暴伴冰雹(小/中)", "⛈️"), 99: ("雷暴伴冰雹(大)", "⛈️"),
}

def zh_weekday(d: date) -> str:
    return ["周一","周二","周三","周四","周五","周六","周日"][ (d.weekday()+0) % 7 ]

def fetch_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def geocode_city(name: str, country_code: str = None) -> Dict[str, Any]:
    """Open-Meteo 地理编码，返回最匹配地点"""
    params = {"name": name, "count": 5, "language": "zh", "format": "json"}
    data = fetch_json("https://geocoding-api.open-meteo.com/v1/search", params)
    results = data.get("results") or []
    if country_code:
        results = [x for x in results if x.get("country_code") == country_code] or results
    if not results:
        raise ValueError(f"未找到城市：{name}")
    return results[0]  # 取第一条最匹配

def get_today_weather(lat: float, lon: float, tz: str = "auto") -> Dict[str, Any]:
    """拉取当前+当日聚合数据"""
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": tz,
        "current": ",".join([
            "temperature_2m","apparent_temperature","relative_humidity_2m",
            "weather_code","wind_speed_10m","wind_gusts_10m","wind_direction_10m",
            "precipitation","rain","showers","snowfall","is_day","cloud_cover"
        ]),
        "daily": ",".join([
            "weather_code","temperature_2m_max","temperature_2m_min",
            "precipitation_probability_max","precipitation_sum",
            "uv_index_max","sunrise","sunset",
            "wind_speed_10m_max","wind_gusts_10m_max"
        ]),
        "forecast_days": 1  # 只要今天
    }
    return fetch_json("https://api.open-meteo.com/v1/forecast", params)

def format_msg(city_name: str, wx: Dict[str, Any]) -> str:
    # 当前实况
    c = wx.get("current", {})
    cur_t = c.get("temperature_2m")
    cur_t_feel = c.get("apparent_temperature")
    cur_hum = c.get("relative_humidity_2m")
    cur_wspd = c.get("wind_speed_10m")
    cur_wgust = c.get("wind_gusts_10m")
    code = c.get("weather_code", 0)
    cond_txt, cond_emoji = WMO_MAP.get(code, ("天气不明", "🌈"))

    # 当日聚合
    d = wx.get("daily", {})
    # daily 的各字段是 list，取第 0 个
    tmax = (d.get("temperature_2m_max") or [None])[0]
    tmin = (d.get("temperature_2m_min") or [None])[0]
    d_code = (d.get("weather_code") or [code])[0]
    d_cond_txt, _ = WMO_MAP.get(d_code, (cond_txt, cond_emoji))
    precip_prob = (d.get("precipitation_probability_max") or [None])[0]
    precip_sum = (d.get("precipitation_sum") or [None])[0]
    sunrise = (d.get("sunrise") or [""])[0][-5:]  # 取 HH:MM
    sunset  = (d.get("sunset") or [""])[0][-5:]
    uv_max  = (d.get("uv_index_max") or [None])[0]
    wspd_max = (d.get("wind_speed_10m_max") or [None])[0]
    wgst_max = (d.get("wind_gusts_10m_max") or [None])[0]
    the_date_str = (d.get("time") or [datetime.now().strftime("%Y-%m-%d")])[0]

    # 贴士规则（可按需扩展）
    tips = []
    if tmax is not None and tmax >= 37:
        tips.append("⚠️ 高温：减少午后外出，多喝水。")
    if uv_max and uv_max >= 7:
        tips.append("🧴 UV 强：防晒+遮阳。")
    if (precip_prob and precip_prob >= 40) or (precip_sum and precip_sum >= 1):
        tips.append("🌂 可能降雨：出门带伞。")
    if wgst_max and wgst_max >= 50:
        tips.append("💨 阵风较大：远离高空坠物。")
    if not tips:
        tips.append("✅ 体感较舒适，注意通风防晒。")

    # 头部
    dt = datetime.strptime(the_date_str, "%Y-%m-%d").date()
    header = f"📍{city_name} | {zh_weekday(dt)}（{the_date_str}）"
    current = f"当前：{cond_emoji}{cond_txt} {round(cur_t)}℃ · 体感{round(cur_t_feel)}℃ · 湿度{cur_hum}% · 风{round(cur_wspd)}km/h"
    today_line = f"今日：{d_cond_txt}，{round(tmin)}–{round(tmax)}℃ · 降雨概率{(str(precip_prob)+'%') if precip_prob is not None else '—'} · 降水量{precip_sum if precip_sum is not None else '—'}mm"
    sun_wind = f"日出 {sunrise}｜日落 {sunset}｜阵风最高 {round(wgst_max)}km/h" if wgst_max is not None else f"日出 {sunrise}｜日落 {sunset}"

    msg = "\n".join([
        header,
        current,
        today_line,
        sun_wind,
        "📝 小贴士：" + tips[0]
    ])
    return msg

def build_todays_message_for_city(city: str = "西安", country_code: str = "CN") -> str:
    place = geocode_city(city, country_code)
    wx = get_today_weather(place["latitude"], place["longitude"], tz="Asia/Shanghai")
    display_name = place.get("name") or city
    # 可附带区/省份信息：display_name = f"{place['name']}·{place.get('admin1','')}".strip("·")
    return format_msg(display_name, wx)

# 设置每天凌晨0:05执行
schedule.every().day.at("00:05").do(send_messages_daily)

if __name__ == "__main__":
    print("抖音自动续火花程序已启动")
    
    # 加载用户配置
    load_user_config()
    
    # 显示交互式菜单
    while True:
        print("\n" + "="*40)
        print("抖音自动续火花 - 菜单")
        print("="*40)
        print("1. 立即执行续火花(当前用户)")
        print("2. 立即为所有用户执行续火花")  # 新选项
        print("3. 列出所有用户")
        print("4. 切换用户")
        print("5. 添加新用户")
        print("6. 编辑用户信息")
        print("7. 删除用户")
        print("8. 刷新当前用户Cookie")
        print("9. 刷新指定用户Cookie")
        print("10. 重复执行续火花")
        print("11. 启动定时任务(每天00:05自动为所有用户发送)")  # 更新描述
        print("0. 退出程序")
        
        choice = input("\n请选择操作: ")
        
        if choice == "1":
            active_user = get_active_user()
            print(f"为用户 [{active_user['name']}] 执行续火花操作")
            send_messages_for_user(active_user)
            
        elif choice == "2":
            # 立即为所有用户执行
            print("开始为所有用户执行续火花操作")
            send_messages_for_all_users()
        
        elif choice == "3":
            list_users()
        
        elif choice == "4":
            list_users()
            user_index = int(input("请输入要切换的用户索引: "))
            switch_user(user_index)
        
        elif choice == "5":
            setup_new_user()
            
        elif choice == "6":
            # 编辑用户信息
            list_users()
            user_index = int(input("请输入要编辑的用户索引: "))
            edit_user(user_index)
            
        elif choice == "7":
            # 删除用户
            list_users()
            user_index = int(input("请输入要删除的用户索引: "))
            if input(f"确定要删除用户 [{USERS[user_index]['name']}]? (y/n): ").lower() == 'y':
                delete_user(user_index)
            
        elif choice == "8":
            # 刷新当前用户的Cookie
            active_user = get_active_user()
            print(f"准备刷新用户 [{active_user['name']}] 的Cookie...")
            refresh_active_user_cookies()
            
        elif choice == "9":
            # 刷新指定用户的Cookie
            list_users()
            user_index = int(input("请输入要刷新Cookie的用户索引: "))
            refresh_user_cookies(user_index)
            
        elif choice == "10":
            # 重复执行续火花
            active_user = get_active_user()
            try:
                repeat_count = int(input("请输入要重复执行的次数: "))
                if repeat_count <= 0:
                    print("重复次数必须大于0")
                    continue
                    
                interval = int(input("请输入每次执行间隔的秒数(建议不小于10秒): "))
                if interval < 3:
                    print("间隔时间太短可能导致操作失败，已自动调整为10秒")
                    interval = 10
                    
                print(f"将为用户 [{active_user['name']}] 重复执行 {repeat_count} 次续火花操作，间隔 {interval} 秒")
                if input("确认执行? (y/n): ").lower() == 'y':
                    send_messages_with_repeat(active_user, repeat_count, interval)
            except ValueError:
                print("请输入有效的数字")
        
        elif choice == "11":
            print("已启动定时任务，将在每天00:05自动为所有用户发送消息")
            print("程序将在后台运行。按Ctrl+C退出。")
            
            # 启动定时任务循环
            while True:
                schedule.run_pending()
                time.sleep(10)
        
        elif choice == "0":
            # 保存用户配置并退出
            save_user_config()
            print("程序已退出")
            break
        
        else:
            print("无效的选择，请重新输入")
