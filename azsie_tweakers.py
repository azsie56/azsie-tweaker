# -*- coding: utf-8 -*-
"""
AZSIE TWEAKER TOOL v1.10
Developed by AZSIE Community

Windows optimization tool - Python + CustomTkinter (Gaming Dark Theme)
ทำงานออฟไลน์ (ยกเว้นตัวนับยอดดาวน์โหลดที่ตั้งค่าเอง) / Offline (except the optional download counter)

pip install customtkinter psutil pillow
"""

# ======================================================================
#  CONFIG
# ======================================================================
SIDEBAR_SIDE = "right"   # "right" = เมนูชิดขวา, "left" = เมนูชิดซ้าย

APP_NAME = "AZSIE TWEAKER TOOL"
APP_VERSION = "1.01"
RESTORE_POINT_NAME = "AZSIE Tweaker Restore Point"

# ลิงก์ Discord ที่แสดงในหน้า Info
DISCORD_URL = "https://discord.gg/fySGjBvVEz"

# ---- ตัวนับยอดดาวน์โหลดในหน้า Dashboard (เลือกอย่างใดอย่างหนึ่ง) ----
GITHUB_REPO = "azsie56/azsie-tweaker"           # เช่น "yourname/azsie-tweaker" -> รวมยอด download ของทุกไฟล์ใน GitHub Releases
DOWNLOAD_STATS_URL = ""    # หรือ URL ที่คืน JSON เช่น {"downloads": 1234}
AUTO_CHECK_UPDATE = True        # ตรวจเวอร์ชันใหม่จาก GitHub Releases ตอนเปิดโปรแกรม (ต้องตั้ง GITHUB_REPO) / Check GitHub for a newer release at startup
AUTO_REFRESH_DOWNLOADS = True   # ดึงยอดอัตโนมัติ 1 ครั้งตอนเปิดโปรแกรม (ถ้าตั้งค่าแหล่งข้อมูลไว้)


# ======================================================================
import os
import sys

if os.name != "nt":
    print("โปรแกรมนี้ใช้ได้เฉพาะ Windows เท่านั้น / This tool only runs on Windows.")
    sys.exit(1)

import ctypes
import ctypes.wintypes as wt
import glob
import json
import math
import platform
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import winreg
from datetime import datetime
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from tkinter import filedialog, messagebox

import customtkinter as ctk
import psutil

# ----------------------------------------------------------------------
#  Theme colors
# ----------------------------------------------------------------------
BG = "#060A12"
PANEL = "#0E1524"
PANEL_2 = "#141D33"
BADGE_BG = "#0A1020"
CARD_BORDER = "#1B2745"
ACCENT = "#3B82F6"
ACCENT_HOVER = "#2563EB"
NAV_HOVER = "#17233F"
TEXT = "#E5E7EB"
SUBTEXT = "#94A3B8"
DANGER = "#DC2626"
DANGER_HOVER = "#B91C1C"
BOOST = "#10B981"          # ปุ่ม One-Click Boost (เขียวมรกต สว่าง น่ากด)
BOOST_HOVER = "#34D399"
DISCORD = "#5865F2"
DISCORD_HOVER = "#4752C4"
SIDEBAR_W = 240

LOG_COLORS = {
    "info": "#CBD5E1", "ok": "#34D399", "err": "#F87171", "warn": "#FBBF24",
    "run": "#60A5FA", "cmd": "#7DD3FC", "dim": "#64748B",
}
LOG_PREFIX = {
    "info": "", "ok": "[OK] ", "err": "[ERROR] ", "warn": "[WARN] ",
    "run": "[RUN] ", "cmd": "> ", "dim": "    ",
}

CREATE_NO_WINDOW = 0x08000000
HKLM = winreg.HKEY_LOCAL_MACHINE
HKCU = winreg.HKEY_CURRENT_USER
SPI_SETMOUSE = 0x0004
SPIF_UPDATEINIFILE = 0x1
SPIF_SENDCHANGE = 0x2

# ----------------------------------------------------------------------
#  Language (TH / EN) - เก็บค่าที่เลือกไว้ในเครื่องเท่านั้น
# ----------------------------------------------------------------------
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA") or tempfile.gettempdir(), "AZSIE Tweaker")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")


def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(data: dict):
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


LANG = load_settings().get("lang", "th")
if LANG not in ("th", "en"):
    LANG = "th"


def L(th: str, en: str) -> str:
    """เลือกข้อความตามภาษาปัจจุบัน"""
    return th if LANG == "th" else en


# ======================================================================
#  Administrator check / auto-elevate
# ======================================================================
def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ensure_admin():
    """ถ้าไม่ได้รันด้วยสิทธิ์ Admin ให้เปิดโปรแกรมใหม่แบบ Run as Administrator"""
    if is_admin():
        return
    if getattr(sys, "frozen", False):
        exe = sys.executable
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
    else:
        exe = sys.executable
        params = " ".join(f'"{a}"' for a in sys.argv)
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    if ret <= 32:
        ctypes.windll.user32.MessageBoxW(
            None,
            L("ต้องใช้สิทธิ์ Administrator ในการใช้งานโปรแกรมนี้",
              "This tool requires Administrator privileges."),
            APP_NAME,
            0x10,
        )
    sys.exit(0)


# ======================================================================
#  Low-level helpers (privileges, memory)
# ======================================================================
class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wt.DWORD), ("HighPart", wt.LONG)]


class LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", LUID), ("Attributes", wt.DWORD)]


class TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [("PrivilegeCount", wt.DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_adv = ctypes.WinDLL("advapi32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)
_ntdll = ctypes.WinDLL("ntdll")
_shell32 = ctypes.WinDLL("shell32")

_k32.GetCurrentProcess.restype = wt.HANDLE
_k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
_k32.OpenProcess.restype = wt.HANDLE
_k32.CloseHandle.argtypes = [wt.HANDLE]
_adv.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
_adv.OpenProcessToken.restype = wt.BOOL
_adv.LookupPrivilegeValueW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, ctypes.POINTER(LUID)]
_adv.LookupPrivilegeValueW.restype = wt.BOOL
_adv.AdjustTokenPrivileges.argtypes = [
    wt.HANDLE, wt.BOOL, ctypes.POINTER(TOKEN_PRIVILEGES), wt.DWORD, ctypes.c_void_p, ctypes.c_void_p,
]
_adv.AdjustTokenPrivileges.restype = wt.BOOL
_psapi.EmptyWorkingSet.argtypes = [wt.HANDLE]
_psapi.EmptyWorkingSet.restype = wt.BOOL
_ntdll.NtSetSystemInformation.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]
_ntdll.NtSetSystemInformation.restype = ctypes.c_long
_shell32.SHEmptyRecycleBinW.argtypes = [wt.HWND, wt.LPCWSTR, wt.DWORD]
_shell32.SHEmptyRecycleBinW.restype = ctypes.c_long

TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_QUERY = 0x0008
SE_PRIVILEGE_ENABLED = 0x00000002
PROCESS_SET_QUOTA = 0x0100
PROCESS_QUERY_INFORMATION = 0x0400
SYSTEM_MEMORY_LIST_INFORMATION = 80
MEMORY_FLUSH_MODIFIED_LIST = 3
MEMORY_PURGE_STANDBY_LIST = 4
SHERB_NOCONFIRMATION = 0x1
SHERB_NOPROGRESSUI = 0x2
SHERB_NOSOUND = 0x4


def enable_privilege(name: str) -> bool:
    token = wt.HANDLE()
    if not _adv.OpenProcessToken(
        _k32.GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, ctypes.byref(token)
    ):
        return False
    try:
        luid = LUID()
        if not _adv.LookupPrivilegeValueW(None, name, ctypes.byref(luid)):
            return False
        tp = TOKEN_PRIVILEGES()
        tp.PrivilegeCount = 1
        tp.Privileges[0].Luid = luid
        tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
        ctypes.set_last_error(0)
        _adv.AdjustTokenPrivileges(token, False, ctypes.byref(tp), 0, None, None)
        return ctypes.get_last_error() == 0
    finally:
        _k32.CloseHandle(token)


def nt_memory_command(command: int) -> int:
    cmd = ctypes.c_int(command)
    return _ntdll.NtSetSystemInformation(
        SYSTEM_MEMORY_LIST_INFORMATION, ctypes.byref(cmd), ctypes.sizeof(cmd)
    )


def fmt_bytes(n: float) -> str:
    n = float(max(n, 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.2f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.2f} TB"


def dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def open_target(target: str):
    """เปิดหน้า Settings / เครื่องมือของ Windows (ms-settings:..., services.msc, ...)"""
    try:
        os.startfile(target)
    except OSError:
        subprocess.Popen(["cmd", "/c", "start", "", target], creationflags=CREATE_NO_WINDOW)


def reg_read(root, path, name, default=None):
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return default


def get_os_name() -> str:
    base = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    product = str(reg_read(HKLM, base, "ProductName", "Windows"))
    build = str(reg_read(HKLM, base, "CurrentBuild", ""))
    ver = reg_read(HKLM, base, "DisplayVersion", "") or reg_read(HKLM, base, "ReleaseId", "")
    try:
        if int(build) >= 22000:  # Windows 11 ยังเขียนว่า "Windows 10" ใน ProductName
            product = product.replace("Windows 10", "Windows 11")
    except ValueError:
        pass
    out = product
    if ver:
        out += f" {ver}"
    if build:
        out += f" (build {build})"
    return out


def get_cpu_name() -> str:
    name = reg_read(HKLM, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString", "")
    return " ".join(str(name).split()) or platform.processor() or "-"


def get_gpu_names() -> list:
    names = []
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11cd-bfc1-08002be10318}"
    try:
        with winreg.OpenKey(HKLM, base, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                if not sub.isdigit():
                    continue
                desc = reg_read(HKLM, base + "\\" + sub, "DriverDesc")
                if desc and desc not in names and "microsoft" not in str(desc).lower():
                    names.append(str(desc))
    except OSError:
        pass
    return names


# ----------------------------------------------------------------------
#  Download counter (ออนไลน์เฉพาะตอนดึงยอดดาวน์โหลดเท่านั้น)
# ----------------------------------------------------------------------
def dl_source() -> str:
    return (GITHUB_REPO or DOWNLOAD_STATS_URL or "").strip()


def _http_json(url: str, timeout: int = 10):
    req = urllib.request.Request(
        url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def fetch_download_stats():
    """คืนค่า (ยอดรวม, [(ชื่อ release, ยอดดาวน์โหลด), ...])"""
    if GITHUB_REPO.strip():
        repo = GITHUB_REPO.strip().strip("/")
        data = _http_json(f"https://api.github.com/repos/{repo}/releases?per_page=100")
        if not isinstance(data, list):
            raise ValueError("unexpected response from GitHub")
        releases, total = [], 0
        for rel in data:
            cnt = sum(int(a.get("download_count", 0)) for a in rel.get("assets", []))
            total += cnt
            releases.append((str(rel.get("tag_name") or rel.get("name") or "?"), cnt))
        return total, releases
    data = _http_json(DOWNLOAD_STATS_URL.strip())
    if isinstance(data, (int, float)):
        return int(data), []
    if isinstance(data, dict):
        for key in ("downloads", "download_count", "total", "count"):
            if key in data:
                return int(data[key]), []
    raise ValueError("JSON must be a number or contain 'downloads'")


def _version_tuple(v: str):
    nums = [int(n) for n in re.findall(r"\d+", str(v))[:4]]
    return tuple(nums + [0] * (4 - len(nums)))


def is_newer_version(latest: str, current: str) -> bool:
    return _version_tuple(latest) > _version_tuple(current)


def fetch_latest_release():
    """คืนค่า {"tag", "url"} ของ Release ล่าสุดบน GitHub หรือ None ถ้ายังไม่มี Release"""
    repo = GITHUB_REPO.strip().strip("/")
    try:
        data = _http_json(f"https://api.github.com/repos/{repo}/releases/latest")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if not isinstance(data, dict):
        raise ValueError("unexpected response from GitHub")
    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    if not tag:
        return None
    url = str(data.get("html_url") or "")
    if not url.startswith("https://github.com/"):
        url = f"https://github.com/{repo}/releases/latest"
    return {"tag": tag, "url": url}


# ======================================================================
#  Smooth widgets
# ======================================================================
def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(c) -> str:
    return "#%02x%02x%02x" % tuple(int(round(x)) for x in c)


class SmoothButton(ctk.CTkButton):
    """ปุ่มที่เปลี่ยนสีตอน Hover แบบค่อย ๆ เฟด"""

    def __init__(self, master, fg_color=ACCENT, hover_color=ACCENT_HOVER, **kwargs):
        kwargs["hover"] = False
        kwargs.setdefault("text_color_disabled", "#7C8AA5")
        super().__init__(master, fg_color=fg_color, **kwargs)
        self._sb_base = fg_color
        self._sb_hover = hover_color
        self._sb_cur = _hex_to_rgb(fg_color)
        self._sb_target = self._sb_cur
        self._sb_job = None
        self.bind("<Enter>", self._sb_enter)
        self.bind("<Leave>", self._sb_leave)

    def _sb_enter(self, _e=None):
        try:
            if self.cget("state") == "disabled":
                return
        except Exception:
            pass
        self._sb_go(self._sb_hover)

    def _sb_leave(self, _e=None):
        self._sb_go(self._sb_base)

    def set_palette(self, base: str, hover: str):
        self._sb_base, self._sb_hover = base, hover
        self._sb_go(base)

    def _sb_go(self, color: str):
        self._sb_target = _hex_to_rgb(color)
        if self._sb_job is None:
            self._sb_step()

    def _sb_step(self):
        try:
            if not self.winfo_exists():
                self._sb_job = None
                return
            cur, tgt = self._sb_cur, self._sb_target
            new = tuple(c + (t - c) * 0.34 for c, t in zip(cur, tgt))
            done = max(abs(t - n) for n, t in zip(new, tgt)) < 1.5
            if done:
                new = tgt
            self._sb_cur = new
            self.configure(fg_color=_rgb_to_hex(new))
            self._sb_job = None if done else self.after(14, self._sb_step)
        except Exception:
            self._sb_job = None


class SmoothScrollFrame(ctk.CTkScrollableFrame):
    """เลื่อนด้วยล้อเมาส์แบบนุ่มนวล (easing)"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ss_target = 0.0
        self._ss_job = None

    def _ss_owns(self, widget) -> bool:
        w = widget
        canvas = getattr(self, "_parent_canvas", None)
        frame = getattr(self, "_parent_frame", None)
        while w is not None and not isinstance(w, str):
            if w is self or w is canvas or w is frame:
                return True
            w = getattr(w, "master", None)
        return False

    def _mouse_wheel_all(self, event):
        try:
            if not self._ss_owns(event.widget):
                return
            canvas = self._parent_canvas
            top, bottom = canvas.yview()
            if (top, bottom) == (0.0, 1.0):
                return
            bbox = canvas.bbox("all")
            total = (bbox[3] - bbox[1]) if bbox else 0
            if total <= 0:
                return
            if self._ss_job is None:
                self._ss_target = top
            step = (event.delta / 120.0) * 110.0 / total
            max_top = max(1.0 - (bottom - top), 0.0)
            self._ss_target = min(max(self._ss_target - step, 0.0), max_top)
            self._ss_animate()
        except Exception:
            try:
                super()._mouse_wheel_all(event)
            except Exception:
                pass

    def _ss_animate(self):
        try:
            canvas = self._parent_canvas
            cur = canvas.yview()[0]
            diff = self._ss_target - cur
            if abs(diff) < 0.0008:
                canvas.yview_moveto(self._ss_target)
                self._ss_job = None
                return
            canvas.yview_moveto(cur + diff * 0.28)
            self._ss_job = self.after(10, self._ss_animate)
        except Exception:
            self._ss_job = None


# ----------------------------------------------------------------------
#  One-Click Boost dial (วาดด้วย Pillow เพื่อให้ขอบเรียบ มี glow และวงโปรเกรส)
# ----------------------------------------------------------------------
_PIL_FONTS = {}


def _pil_font(size: int):
    """ฟอนต์ตัวหนาสำหรับวาดตัวอักษรภาษาอังกฤษ/ตัวเลขบนปุ่มวงกลม (มี fallback)"""
    size = max(int(size), 6)
    if size in _PIL_FONTS:
        return _PIL_FONTS[size]
    win_fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    font = None
    for cand in (os.path.join(win_fonts, "segoeuib.ttf"), os.path.join(win_fonts, "arialbd.ttf"),
                 "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(cand, size)
            break
        except OSError:
            continue
    if font is None:
        try:
            font = ImageFont.load_default(size)   # Pillow 10.1+ รองรับกำหนดขนาด
        except TypeError:
            font = ImageFont.load_default()
    _PIL_FONTS[size] = font
    return font


def _draw_centered(d, xy, text, font, fill):
    try:
        d.text(xy, text, font=font, fill=fill, anchor="mm")
    except (ValueError, TypeError):  # ฟอนต์ที่ไม่รองรับ anchor
        w, h = d.textbbox((0, 0), text, font=font)[2:]
        d.text((xy[0] - w / 2, xy[1] - h / 2), text, font=font, fill=fill)


def _mix(c1: str, c2: str, k: float) -> str:
    a, b = _hex_to_rgb(c1), _hex_to_rgb(c2)
    return _rgb_to_hex(tuple(x + (y - x) * k for x, y in zip(a, b)))


class BoostDial(ctk.CTkLabel):
    """ปุ่มวงกลม One-Click Boost: มี glow เต้นเบา ๆ, วงสแกนหมุนตอนว่าง,
    วงโปรเกรส + เปอร์เซ็นต์ตอนทำงาน และเครื่องหมายถูกเมื่อเสร็จ"""

    HIDPI = 2   # ภาพละเอียดเป็น 2 เท่าของขนาดที่แสดง (คมบนจอ HiDPI)
    SS = 2      # supersampling เพื่อให้ขอบเรียบ

    def __init__(self, master, size=250, command=None):
        super().__init__(master, text="", width=size, height=size, fg_color="transparent")
        self.size = size
        self._command = command
        self.state = "idle"          # idle | busy | done
        self.progress = 0.0          # ค่าที่แสดงอยู่ (เคลื่อนเข้าหา target แบบนุ่ม ๆ)
        self.target = 0.0
        self._phase = 0.0
        self._rot = 0.0
        self._hover = 0.0
        self._hover_target = 0.0
        self._glow_cache = {}
        self._disc_cache = {}
        blank = Image.new("RGBA", (size * self.HIDPI, size * self.HIDPI), (0, 0, 0, 0))
        self._ctk_img = ctk.CTkImage(light_image=blank, dark_image=blank, size=(size, size))
        self.configure(image=self._ctk_img)
        for w in (getattr(self, "_label", None), getattr(self, "_canvas", None)):
            try:
                w.configure(cursor="hand2")
            except Exception:
                pass
        self.bind("<Enter>", lambda _e: self._set_hover(1.0))
        self.bind("<Leave>", lambda _e: self._set_hover(0.0))
        self.bind("<Button-1>", self._on_click)
        self._render()

    # ---- public API ---------------------------------------------------
    def begin(self):
        self.state, self.progress, self.target = "busy", 0.0, 0.03

    def set_target(self, p: float):
        self.target = max(0.0, min(1.0, p))

    def finish(self):
        self.state, self.target = "done", 1.0

    def set_busy(self, busy: bool):
        if busy and self.state != "busy":
            self.begin()
        elif not busy and self.state == "busy":
            self.state = "idle"
            self.progress = self.target = 0.0

    # ---- interaction --------------------------------------------------
    def _set_hover(self, v: float):
        self._hover_target = 0.0 if self.state == "busy" else v

    def _on_click(self, e):
        if self.state == "busy" or not self._command:
            return
        r = self.size / 2
        if math.hypot(e.x - r, e.y - r) <= self.size * 0.46:
            self._command()

    # ---- animation ----------------------------------------------------
    def tick(self, dt: float):
        dt = max(0.0, min(dt, 0.1))
        self._phase += dt * (3.4 if self.state == "busy" else 2.2)
        self._rot = (self._rot + dt * (260 if self.state == "busy" else 110)) % 360
        self._hover += (self._hover_target - self._hover) * min(1.0, dt * 12)
        self.progress += (self.target - self.progress) * min(1.0, dt * 4)
        self._render()

    # ---- drawing ------------------------------------------------------
    def _glow(self, F: int, color: str):
        """glow ที่ความละเอียดสุดท้าย (เบลอครั้งเดียวแล้วแคชไว้)"""
        key = (F, color)
        if key not in self._glow_cache:
            u = F / 250.0
            layer = Image.new("RGBA", (F, F), _hex_to_rgb(color) + (0,))
            ImageDraw.Draw(layer).ellipse(
                (F / 2 - 90 * u, F / 2 - 90 * u, F / 2 + 90 * u, F / 2 + 90 * u),
                fill=_hex_to_rgb(color) + (255,))
            self._glow_cache[key] = layer.filter(ImageFilter.GaussianBlur(14 * u))
        return self._glow_cache[key]

    def _disc(self, F: int, outer: str, inner: str, radius_u: float):
        """แผ่นกลางไล่สี วาดแบบ supersample แล้วย่อ แคชไว้ตามสี"""
        key = (F, outer, inner, round(radius_u, 1))
        if key not in self._disc_cache:
            S = F * self.SS
            u = S / 250.0
            c = S / 2
            layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            steps = 28
            for i in range(steps):
                t = i / (steps - 1)
                r = radius_u * u * (1 - 0.55 * t)
                cy = c - radius_u * u * 0.22 * t
                d.ellipse((c - r, cy - r, c + r, cy + r), fill=_mix(outer, inner, t ** 0.8))
            if len(self._disc_cache) > 40:
                self._disc_cache.clear()
            self._disc_cache[key] = layer.reduce(self.SS)
        return self._disc_cache[key]

    def _render(self):
        F = self.size * self.HIDPI          # ขนาดภาพสุดท้าย (px)
        S = F * self.SS                     # ขนาดชั้นวาดเส้น (supersample)
        u = S / 250.0
        c = S / 2
        pulse = (math.sin(self._phase) + 1) / 2
        busy, done = self.state == "busy", self.state == "done"
        hv = round(self._hover * 4) / 4

        # ชั้นล่าง: glow + แผ่นกลาง (ทำที่ความละเอียดสุดท้ายเพื่อให้เร็ว)
        k = (0.55 + 0.25 * pulse) if busy else (0.50 + 0.30 * pulse + 0.25 * hv)
        glow = self._glow(F, BOOST)
        a = glow.getchannel("A").point(lambda v, k=k: int(v * k))
        img = glow.copy()
        img.putalpha(a)
        if busy:
            outer, inner = "#13261F", "#24443A"
        else:
            outer = _mix("#047857", "#10B981", hv)
            inner = _mix("#34D399", "#86EFAC", hv)
        disc_r = 80 * (1 + 0.03 * hv)
        img.alpha_composite(self._disc(F, outer, inner, disc_r))

        # ชั้นบน: วงแหวน ไอคอน ตัวอักษร (supersample)
        layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        ring_r, ring_w = 100 * u, max(int(7 * u), 2)
        box = (c - ring_r, c - ring_r, c + ring_r, c + ring_r)
        mid_r = ring_r - ring_w / 2          # PIL วาดเส้นหนาเข้าด้านในของกรอบ

        def tip(angle_deg, fill):
            x = c + mid_r * math.cos(math.radians(angle_deg))
            y = c + mid_r * math.sin(math.radians(angle_deg))
            rr = ring_w / 2
            d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=fill)

        # วงราง
        d.ellipse(box, outline=_mix(PANEL_2, BOOST, 0.16 if not (busy or done) else 0.08), width=ring_w)
        if busy or done:
            p = max(self.progress, 0.012)
            start, end = -90, -90 + 360 * min(p, 1.0)
            if p >= 0.999:
                d.ellipse(box, outline=BOOST, width=ring_w)
            else:
                d.arc(box, start, end, fill=BOOST, width=ring_w)
                tip(start, BOOST)
                tip(end, "#A7F3D0")
            if busy:  # แสงวิ่งบนวง
                sweep = (self._rot % 360) - 90
                d.arc(box, sweep, sweep + 26, fill=_mix(BOOST, "#FFFFFF", 0.55), width=max(ring_w - int(2 * u), 2))
        else:
            seg_start = self._rot - 90
            d.arc(box, seg_start, seg_start + 78, fill=_mix(BOOST, "#FFFFFF", 0.10 + 0.25 * pulse), width=ring_w)
            tip(seg_start, BOOST)
            tip(seg_start + 78, BOOST)

        rr = disc_r * u
        d.ellipse((c - rr, c - rr, c + rr, c + rr), outline=_mix(outer, "#FFFFFF", 0.18), width=max(int(1.5 * u), 1))

        dark, light = "#04150E", "#E8FFF6"
        if busy:
            _draw_centered(d, (c, c - 6 * u), f"{int(round(self.progress * 100))}%",
                           _pil_font(int(44 * u)), light)
            _draw_centered(d, (c, c + 30 * u), "BOOSTING", _pil_font(int(12 * u)), _mix(BOOST, "#FFFFFF", 0.35))
        elif done:
            w = max(int(9 * u), 3)
            pts = [(c - 27 * u, c - 6 * u), (c - 9 * u, c + 12 * u), (c + 28 * u, c - 26 * u)]
            d.line(pts, fill=dark, width=w, joint="curve")
            for x, y in (pts[0], pts[-1]):
                d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=dark)
            _draw_centered(d, (c, c + 36 * u), "DONE", _pil_font(int(16 * u)), dark)
        else:
            iy, ir, w = c - 14 * u, 25 * u, max(int(6.5 * u), 3)
            d.arc((c - ir, iy - ir, c + ir, iy + ir), -55, 235, fill=dark, width=w)
            for ang in (-55, 235):
                x = c + (ir - w / 2) * math.cos(math.radians(ang))
                y = iy + (ir - w / 2) * math.sin(math.radians(ang))
                d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=dark)
            d.line((c, iy - ir - 4 * u, c, iy - 2 * u), fill=dark, width=w)
            d.ellipse((c - w / 2, iy - ir - 4 * u - w / 2, c + w / 2, iy - ir - 4 * u + w / 2), fill=dark)
            _draw_centered(d, (c, c + 38 * u), "BOOST", _pil_font(int(19 * u)), dark)

        img.alpha_composite(layer.reduce(self.SS))
        self._ctk_img.configure(light_image=img, dark_image=img)



# ======================================================================
#  Content definitions (TH, EN)
# ======================================================================
NAV = [
    ("dashboard", ("แดชบอร์ด / ข้อมูลระบบ", "Dashboard / System Info")),
    ("basic", ("การปรับแต่งพื้นฐาน", "Basic Tweaks")),
    ("adv", ("การปรับแต่งขั้นสูง", "Advanced Tweaks")),
    ("short", ("ทางลัดเร่งความเร็ว", "Speed-Up Shortcuts")),
    ("boost", ("บูสต์คลิกเดียว", "One-Click Boost")),
    ("info", ("ข้อมูล (Info)", "Info")),
]

PAGE_SUB = {
    "dashboard": ("ดูสถานะเครื่องแบบเรียลไทม์ ข้อมูลระบบ และยอดดาวน์โหลดของแอป",
                  "Live PC status, system info and the app's download count"),
    "basic": ("ล้างไฟล์ขยะ ล้าง RAM ซ่อมแซมระบบ และรีเซ็ตเครือข่าย",
              "Clean junk, free RAM, repair the system and reset the network"),
    "adv": ("ปรับแต่งระบบเชิงลึกเพื่อประสิทธิภาพ ลดความหน่วง และความเป็นส่วนตัว",
            "Deeper Windows tuning for performance, lower latency and privacy"),
    "short": ("ทางลัดไปยังหน้าตั้งค่าที่ใช้ปิดสิ่งที่ทำให้เครื่องช้า",
              "Shortcuts to the Windows pages where you can switch off what slows your PC"),
    "boost": ("เลือกโปรไฟล์ แล้วกดปุ่มเดียว ปรับแต่งอัตโนมัติ พร้อมดูความคืบหน้าแบบสด",
              "Pick a profile, press one button, watch every step run live"),
    "info": ("ข้อมูลโปรแกรมและลิงก์ชุมชน", "About this tool and community links"),
}

# (title, description, method name)
BASIC_CLEANUP = [
    (("ล้างไฟล์ขยะทั้งหมด", "Clean All Junk Files"),
     ("ลบไฟล์ใน %temp%, C:\\Windows\\Temp และ C:\\Windows\\Prefetch",
      "Delete files in %temp%, C:\\Windows\\Temp and C:\\Windows\\Prefetch"),
     "task_clean_junk"),
    (("ล้างแคช Windows Update", "Clear Windows Update Cache"),
     ("หยุดบริการอัปเดตชั่วคราว ลบไฟล์ใน SoftwareDistribution\\Download แล้วเปิดบริการกลับ",
      "Temporarily stop update services, delete SoftwareDistribution\\Download, then restore them"),
     "task_update_cache"),
    (("ล้างแคชเบราว์เซอร์", "Clear Browser Caches"),
     ("ล้างแคชของ Chrome, Edge, Brave และ Firefox เท่านั้น (ไม่ลบรหัสผ่านหรือประวัติ แนะนำให้ปิดเบราว์เซอร์ก่อน)",
      "Clear Chrome, Edge, Brave and Firefox caches only (no passwords or history; close browsers first)"),
     "task_browser_cache"),
    (("ล้างแคชรูปย่อและไอคอน", "Clear Thumbnail & Icon Cache"),
     ("ลบ thumbcache และ iconcache ของ Explorer (Windows จะสร้างใหม่เอง)",
      "Delete Explorer thumbcache and iconcache files (Windows rebuilds them)"),
     "task_thumbnails"),
    (("ล้าง Crash Dump และรายงานข้อผิดพลาด", "Clear Crash Dumps & Error Reports"),
     ("ลบ Minidump, MEMORY.DMP, CrashDumps และรายงานของ Windows Error Reporting",
      "Delete Minidump, MEMORY.DMP, CrashDumps and Windows Error Reporting files"),
     "task_crash_dumps"),
    (("ล้างแคช Shader ของเกม/การ์ดจอ", "Clear Shader Caches (GPU / Games)"),
     ("ลบแคช Shader ของ DirectX, NVIDIA, AMD และ Intel ที่สะสมจนบวม (เกมจะสร้างใหม่เอง "
      "การเปิดเกมครั้งแรกหลังล้างอาจกระตุกเล็กน้อย)",
      "Delete bloated DirectX, NVIDIA, AMD and Intel shader caches (games rebuild them; "
      "the first launch afterwards may stutter a little)"),
     "task_shader_cache"),
    (("ล้างบันทึกระบบและแคช Delivery Optimization", "Clear System Logs & Delivery Optimization Cache"),
     ("ลบ log ของ CBS/DISM/Windows Update และแคชไฟล์อัปเดตที่แชร์ให้เครื่องอื่น (ไฟล์ที่ระบบใช้งานอยู่จะถูกข้าม)",
      "Delete CBS/DISM/Windows Update logs and the cached update files shared with other PCs "
      "(files in use are skipped)"),
     "task_sys_logs"),
    (("ล้างถังขยะ", "Empty Recycle Bin"),
     ("ลบไฟล์ทั้งหมดในถังขยะของทุกไดรฟ์ (กู้คืนไม่ได้)",
      "Permanently delete everything in the Recycle Bin on all drives"),
     "task_recycle_bin"),
]

BASIC_SYSTEM = [
    (("ล้างแคช RAM", "Optimize RAM Cache"),
     ("ล้าง RAM Standby List และเคลียร์ Memory Working Set",
      "Clear the RAM Standby List and trim process Working Sets"),
     "task_optimize_ram"),
    (("ปรับแต่ง SSD (TRIM)", "Optimize SSD (TRIM)"),
     ("ตรวจว่าไดรฟ์ระบบเป็น SSD หรือไม่ ถ้าใช่จะสั่ง ReTrim เพื่อคืนบล็อกที่ว่างให้ SSD (HDD จะถูกข้ามอัตโนมัติ)",
      "Check whether the system drive is an SSD and, if so, run ReTrim so free blocks are returned to it "
      "(HDDs are skipped automatically)"),
     "task_retrim"),
    (("ล้าง DNS และรีเซ็ตเครือข่าย", "Flush DNS & Reset Network"),
     ("ipconfig /flushdns, netsh winsock reset, netsh int ip reset (ต้องรีสตาร์ทเครื่อง)",
      "ipconfig /flushdns, netsh winsock reset, netsh int ip reset (restart required)"),
     "task_network"),
    (("ล้างไฟล์ส่วนประกอบเก่าของ Windows", "Clean Windows Component Store"),
     ("รัน DISM StartComponentCleanup เพื่อลบไฟล์อัปเดตเก่า อาจใช้เวลาหลายนาที",
      "Run DISM StartComponentCleanup to remove superseded update files. May take several minutes"),
     "task_dism"),
    (("สแกนและซ่อมแซมไฟล์ระบบ", "Scan & Repair System Files"),
     ("รัน sfc /scannow เพื่อตรวจและซ่อมไฟล์ระบบที่เสียหาย อาจใช้เวลา 10-30 นาที",
      "Run sfc /scannow to check and repair corrupted system files. May take 10-30 minutes"),
     "task_sfc"),
]

# (ชื่อกลุ่ม, [ (ชื่อ, คำอธิบาย, ชื่อเมธอด[, ตัวเลือก]) ])
# ตัวเลือก: {"confirm": (TH, EN) ถามยืนยันก่อนรัน, "btn": (TH, EN) ข้อความบนปุ่ม}
# เมธอดที่ขึ้นต้นด้วย ask_ จะถูกเรียกบน UI thread (ใช้เปิดหน้าต่างเลือกไฟล์)
ADVANCED_GROUPS = [
    (("ประสิทธิภาพและความหน่วง", "Performance & Latency"), [
        (("เปิด Ultimate Performance", "Enable Ultimate Performance"),
         ("เปิดใช้งานแผนพลังงาน Ultimate Performance ด้วย powercfg",
          "Activate the Ultimate Performance power plan via powercfg"),
         "task_ultimate_power"),
        (("ปิด Mouse Acceleration", "Disable Mouse Acceleration"),
         ("ปิด Enhance pointer precision ผ่าน Registry ของเมาส์ (MouseSpeed, MouseThreshold1/2) "
          "ให้เมาส์เคลื่อนที่ 1:1 มีผลทันที",
          "Turn off Enhance pointer precision via the mouse registry values (MouseSpeed, "
          "MouseThreshold1/2) for 1:1 movement. Applies immediately"),
         "task_mouse_accel"),
        (("ปิด Network Throttling และตั้ง SystemResponsiveness",
          "Disable Network Throttling & Set SystemResponsiveness"),
         ("ปิด NetworkThrottlingIndex และตั้ง SystemResponsiveness = 0 เพื่อให้เกมได้ทรัพยากรมากขึ้น "
          "(ต้องรีสตาร์ทเครื่อง)",
          "Disable NetworkThrottlingIndex and set SystemResponsiveness = 0 so games get more "
          "resources (restart required)"),
         "task_net_throttle"),
        (("เปิด Hardware-accelerated GPU Scheduling", "Enable Hardware-accelerated GPU Scheduling"),
         ("ตั้งค่า HwSchMode = 2 ต้องใช้ Windows 10 2004 ขึ้นไป พร้อมการ์ดจอและไดรเวอร์ที่รองรับ "
          "(ต้องรีสตาร์ทเครื่อง)",
          "Set HwSchMode = 2. Needs Windows 10 2004 or newer plus a supported GPU and driver "
          "(restart required)"),
         "task_hags"),
        (("ตั้ง Visual Effects เป็น Best Performance", "Set Visual Effects to Best Performance"),
         ("ปิดแอนิเมชัน เงา และความโปร่งใส เหมือนเลือก Adjust for best performance "
          "(ออกจากระบบแล้วเข้าใหม่เพื่อให้มีผลครบ)",
          "Turn off animations, shadows and transparency like Adjust for best performance "
          "(sign out and in again for full effect)"),
         "task_visual_fx"),
        (("ปิด Xbox Game Bar และ DVR", "Disable Xbox Game Bar & DVR"),
         ("ปรับ Registry ปิด AppCaptureEnabled และ GameDVR_Enabled เพื่อลด Input Lag",
          "Set AppCaptureEnabled and GameDVR_Enabled to 0 in the registry to reduce input lag"),
         "task_gamebar"),
        (("ปิด HPET", "Disable HPET"),
         ("bcdedit /deletevalue useplatformclock ลดความหน่วงเมาส์/คีย์บอร์ด (ต้องรีสตาร์ทเครื่อง)",
          "bcdedit /deletevalue useplatformclock to reduce mouse/keyboard latency (restart required)"),
         "task_hpet"),
        (("ปิด Power Throttling", "Disable Power Throttling"),
         ("ตั้ง PowerThrottlingOff = 1 ไม่ให้ Windows หน่วงความเร็วโปรเซสเบื้องหลัง/เกมเพื่อประหยัดไฟ "
          "(โน้ตบุ๊กอาจกินแบตมากขึ้น ต้องรีสตาร์ทเครื่อง)",
          "Set PowerThrottlingOff = 1 so Windows stops slowing background processes and games to save power "
          "(laptops may use more battery; restart required)"),
         "task_power_throttle"),
        (("เพิ่มลำดับความสำคัญให้โปรแกรมที่ใช้งานอยู่", "Boost Foreground App Priority"),
         ("ตั้ง Win32PrioritySeparation = 0x26 ให้โปรแกรม/เกมที่อยู่หน้าจอได้เวลา CPU มากขึ้น ตอบสนองไวขึ้น "
          "(ต้องรีสตาร์ทเครื่อง)",
          "Set Win32PrioritySeparation = 0x26 so the app or game in front gets more CPU time and responds faster "
          "(restart required)"),
         "task_priority_sep"),
        (("ตั้ง MMCSS ให้เกมได้ทรัพยากรสูงสุด", "Give Games Top MMCSS Priority"),
         ("ปรับ Tasks\\Games ใน MMCSS: GPU Priority 8, Priority 6, Scheduling Category High, SFIO Priority High "
          "(ต้องรีสตาร์ทเครื่อง)",
          "Tune the MMCSS Tasks\\Games profile: GPU Priority 8, Priority 6, Scheduling Category High, "
          "SFIO Priority High (restart required)"),
         "task_mmcss_games"),
        (("ปิด Nagle Algorithm (ลด Ping)", "Disable Nagle's Algorithm (Lower Ping)"),
         ("ตั้ง TcpAckFrequency = 1 และ TCPNoDelay = 1 กับการ์ดเครือข่ายที่ใช้งานอยู่ ลดหน่วงของแพ็กเก็ตเล็กในเกมออนไลน์ "
          "(ต้องรีสตาร์ทเครื่อง)",
          "Set TcpAckFrequency = 1 and TCPNoDelay = 1 on active network adapters to cut small-packet delay in "
          "online games (restart required)"),
         "task_nagle"),
        (("เปิด Game Mode", "Enable Game Mode"),
         ("เปิด Game Mode ของ Windows ให้จัดลำดับทรัพยากรให้เกมที่กำลังเล่นและลดการแย่ง CPU จากงานเบื้องหลัง",
          "Turn on Windows Game Mode so the game you are playing gets priority over background work"),
         "task_game_mode"),
        (("ลดความหน่วง UI และ Startup Delay", "Faster UI & No Startup Delay"),
         ("ตั้ง MenuShowDelay = 0 และลบ Startup delay ของโปรแกรมที่เปิดตอนเข้า Windows ให้เดสก์ท็อปพร้อมใช้เร็วขึ้น "
          "(ออกจากระบบแล้วเข้าใหม่เพื่อให้มีผล)",
          "Set MenuShowDelay = 0 and remove the startup-app delay so the desktop is ready sooner "
          "(sign out and in for it to apply)"),
         "task_ui_delay"),
        (("ปิดเครื่องเร็วขึ้น", "Faster Shutdown"),
         ("ลดเวลารอปิดบริการและโปรแกรมตอน Shutdown (WaitToKillServiceTimeout 3 วินาที, WaitToKillAppTimeout 5 วินาที, "
          "HungAppTimeout 3 วินาที)",
          "Shorten how long Windows waits for services and apps on shutdown (WaitToKillServiceTimeout 3 s, "
          "WaitToKillAppTimeout 5 s, HungAppTimeout 3 s)"),
         "task_fast_shutdown"),
        (("ปิด Hibernate (คืนพื้นที่ hiberfil.sys)", "Disable Hibernate (Free hiberfil.sys)"),
         ("powercfg /h off ลบไฟล์ hiberfil.sys ที่กินพื้นที่หลาย GB และปิด Fast Startup/Hibernate "
          "เปิดกลับได้จากปุ่ม \"เปิด Hibernate กลับ\"",
          "powercfg /h off removes the multi-GB hiberfil.sys and turns off Fast Startup/Hibernate. "
          "Undo it with the \"Re-enable Hibernate\" button"),
         "task_hibernate_off",
         {"confirm": (
             "ปิด Hibernate หรือไม่?\n\nจะลบ hiberfil.sys และปิด Fast Startup ด้วย "
             "เครื่องอาจบูตช้าลงเล็กน้อยบน HDD แต่ได้พื้นที่ดิสก์คืนหลาย GB",
             "Disable Hibernate?\n\nThis deletes hiberfil.sys and also turns off Fast Startup. "
             "Boot may be slightly slower on an HDD, but you get several GB of disk space back."),
          "btn": ("ปิด", "DISABLE")}),
        (("เปิด Hibernate กลับ", "Re-enable Hibernate"),
         ("powercfg /h on สร้าง hiberfil.sys และเปิด Hibernate/Fast Startup กลับมา",
          "powercfg /h on recreates hiberfil.sys and brings Hibernate/Fast Startup back"),
         "task_hibernate_on"),
    ]),
    (("ความเป็นส่วนตัวและหน้าตา", "Privacy & Interface"), [
        (("ปิดบริการ Telemetry", "Disable Telemetry Services"),
         ("ปิดบริการ DiagTrack และ dmwappushservice",
          "Stop and disable DiagTrack and dmwappushservice"),
         "task_telemetry"),
        (("ปิด Widgets คำแนะนำ และโฆษณาใน Start Menu",
          "Disable Widgets, Suggestions & Ads in Start Menu"),
         ("ปิด Widgets/News, แอปแนะนำ, ส่วน Recommended และโฆษณาใน Start Menu รวมถึงคำแนะนำของ Windows "
          "(Windows บางรุ่นล็อกบางค่าไว้ ออกจากระบบแล้วเข้าใหม่เพื่อให้มีผลครบ)",
          "Turn off Widgets/News, suggested apps, the Recommended section and Start Menu ads plus "
          "Windows tips (some values are locked on newer builds; sign out and in for full effect)"),
         "task_start_clean"),
        (("ปิด Activity History และการติดตามภาษา", "Disable Activity History & Language Tracking"),
         ("ปิดการเก็บและอัปโหลดประวัติกิจกรรม (Timeline) และไม่ส่งรายการภาษาให้เว็บไซต์ "
          "(ออกจากระบบแล้วเข้าใหม่เพื่อให้มีผลครบ)",
          "Stop collecting and uploading Activity History (Timeline) and stop sharing your language list "
          "with websites (sign out and in for full effect)"),
         "task_activity_history"),
        (("ปิดการค้นหาเว็บ (Bing) ใน Start Menu", "Disable Web (Bing) Search in Start Menu"),
         ("ให้ช่องค้นหาของ Start ค้นเฉพาะในเครื่อง ไม่ส่งคำค้นไปที่ Bing ทำให้ผลลัพธ์ขึ้นไวกว่าเดิม",
          "Make Start search look only on this PC instead of sending queries to Bing, so results appear faster"),
         "task_bing_search"),
        (("ปิดแอปเบื้องหลังของ Microsoft Store", "Turn Off Store Apps Running in Background"),
         ("ตั้ง GlobalUserDisabled = 1 ไม่ให้แอป Store แอบรันเบื้องหลัง ลดการกิน RAM/CPU/เน็ต "
          "(การแจ้งเตือนของแอปบางตัวอาจช้าลง เปิดกลับได้ที่หน้า Background Apps)",
          "Set GlobalUserDisabled = 1 so Store apps stop running in the background, saving RAM/CPU/network "
          "(notifications of some apps may be delayed; undo on the Background Apps page)"),
         "task_bg_apps"),
    ]),
    (("ตั้งค่าแยกรายโปรแกรม", "Per-App Settings"), [
        (("ปิด Fullscreen Optimizations ต่อเกม", "Disable Fullscreen Optimizations (per game)"),
         ("เลือกไฟล์ .exe ของเกม แล้วโปรแกรมจะตั้งค่า Disable fullscreen optimizations ให้เกมนั้นโดยเฉพาะ",
          "Pick a game's .exe and the tool sets Disable fullscreen optimizations for that game only"),
         "ask_fso_disable", {"btn": ("เลือกเกม", "PICK GAME")}),
        (("คืนค่า Fullscreen Optimizations ต่อเกม", "Restore Fullscreen Optimizations (per game)"),
         ("เลือกไฟล์ .exe ของเกมที่เคยปิดไว้ เพื่อเปิด Fullscreen Optimizations กลับ",
          "Pick a game's .exe you changed before to turn Fullscreen Optimizations back on"),
         "ask_fso_enable", {"btn": ("เลือกเกม", "PICK GAME")}),
        (("ตั้งการ์ดจอให้เกม: High Performance", "Set Game GPU: High Performance"),
         ("เลือกไฟล์ .exe ของเกม แล้วตั้ง GPU Preference เป็น High performance (การ์ดจอแยก) "
          "เหมาะกับโน้ตบุ๊กที่มีการ์ดจอ 2 ตัว เพราะเกมจะไม่ไปรันบนการ์ดจอออนบอร์ด (เปิดเกมใหม่เพื่อให้มีผล)",
          "Pick a game's .exe and set its GPU Preference to High performance (discrete GPU). "
          "Great for laptops with two GPUs so the game doesn't run on the integrated one (relaunch the game)"),
         "ask_gpu_high", {"btn": ("เลือกเกม", "PICK GAME")}),
        (("ตั้งการ์ดจอให้เกม: Power Saving", "Set Game GPU: Power Saving"),
         ("เลือกไฟล์ .exe ของเกม แล้วตั้ง GPU Preference เป็น Power saving (การ์ดจอออนบอร์ด) เพื่อประหยัดแบต",
          "Pick a game's .exe and set its GPU Preference to Power saving (integrated GPU) to save battery"),
         "ask_gpu_saving", {"btn": ("เลือกเกม", "PICK GAME")}),
        (("คืนค่าการ์ดจอของเกม", "Reset Game GPU Preference"),
         ("เลือกไฟล์ .exe ของเกมที่เคยตั้งไว้ เพื่อคืนเป็นค่า Windows ตัดสินใจเอง",
          "Pick a game's .exe you changed before to let Windows decide the GPU again"),
         "ask_gpu_reset", {"btn": ("เลือกเกม", "PICK GAME")}),
    ]),
    (("ความปลอดภัยและอัปเดต (ใช้ด้วยความระวัง)", "Security & Updates (Use With Care)"), [
        (("ปิด Windows Defender ถาวร", "Disable Windows Defender Permanently"),
         ("ปิดการป้องกันแบบเรียลไทม์และตั้งนโยบายปิด Defender ไว้ถาวร เครื่องจะไม่มีการป้องกันไวรัส "
          "(ถ้าเปิด Tamper Protection อยู่ ต้องปิดที่ Windows Security ก่อน)",
          "Turn off real-time protection and set the policy that keeps Defender off permanently. "
          "Your PC will have no antivirus (if Tamper Protection is on, turn it off in Windows Security first)"),
         "task_defender_off",
         {"confirm": (
             "ปิด Windows Defender ถาวรหรือไม่?\n\n"
             "เครื่องจะไม่มีการป้องกันไวรัสและมัลแวร์แบบเรียลไทม์ แนะนำเฉพาะเมื่อคุณมีโปรแกรมป้องกันอื่นอยู่แล้ว "
             "หรือเข้าใจความเสี่ยงดี\n\n"
             "สามารถเปิดกลับได้จากปุ่ม \"เปิด Windows Defender กลับ\"",
             "Disable Windows Defender permanently?\n\n"
             "Your PC will have no real-time virus or malware protection. Only do this if you already use "
             "another security product or fully understand the risk.\n\n"
             "You can undo it with the \"Re-enable Windows Defender\" button."),
          "btn": ("ปิดถาวร", "DISABLE")}),
        (("เปิด Windows Defender กลับ", "Re-enable Windows Defender"),
         ("ลบนโยบายที่ปิด Defender และเปิดการป้องกันแบบเรียลไทม์กลับมา",
          "Remove the policies that turn Defender off and switch real-time protection back on"),
         "task_defender_on"),
        (("ปิด Windows Update ถาวร", "Disable Windows Update Permanently"),
         ("ตั้งนโยบายไม่อัปเดตอัตโนมัติ ปิดบริการ wuauserv/UsoSvc และงานตั้งเวลาที่เกี่ยวข้อง "
          "จะไม่ได้รับแพตช์ความปลอดภัยจนกว่าจะเปิดกลับ",
          "Set the no-auto-update policy, disable the wuauserv/UsoSvc services and related scheduled "
          "tasks. You will get no security patches until you turn it back on"),
         "task_wupdate_off",
         {"confirm": (
             "ปิด Windows Update ถาวรหรือไม่?\n\n"
             "เครื่องจะไม่ได้รับแพตช์ความปลอดภัยและไดรเวอร์จาก Windows Update จนกว่าจะเปิดกลับ\n\n"
             "สามารถเปิดกลับได้จากปุ่ม \"เปิด Windows Update กลับ\"",
             "Disable Windows Update permanently?\n\n"
             "Your PC will stop receiving security patches and drivers from Windows Update until you "
             "turn it back on.\n\n"
             "You can undo it with the \"Re-enable Windows Update\" button."),
          "btn": ("ปิดถาวร", "DISABLE")}),
        (("เปิด Windows Update กลับ", "Re-enable Windows Update"),
         ("ลบนโยบายที่ปิดอัปเดต คืนค่าบริการและงานตั้งเวลาให้ Windows Update ทำงานปกติ",
          "Remove the update policies and restore the services and scheduled tasks"),
         "task_wupdate_on"),
    ]),
]


# ขั้นตอนที่ One-Click Boost เลือกใช้ได้: key -> (ชื่อ TH/EN, ชื่อเมธอด)
BOOST_STEPS = {
    "restore": (("จุดคืนค่าระบบ", "Restore Point"), "task_restore_point"),
    "junk": (("ล้างไฟล์ขยะ", "Junk Files"), "task_clean_junk"),
    "update_cache": (("แคช Windows Update", "Windows Update Cache"), "task_update_cache"),
    "browser": (("แคชเบราว์เซอร์", "Browser Caches"), "task_browser_cache"),
    "thumbs": (("แคชรูปย่อและไอคอน", "Thumbnail & Icon Cache"), "task_thumbnails"),
    "dumps": (("Crash Dump", "Crash Dumps"), "task_crash_dumps"),
    "logs": (("บันทึกระบบและแคชอัปเดต", "System Logs & Delivery Cache"), "task_sys_logs"),
    "recycle": (("ถังขยะ", "Recycle Bin"), "task_recycle_bin"),
    "ram": (("ล้างแคช RAM", "RAM Cache"), "task_optimize_ram"),
    "network": (("รีเซ็ตเครือข่าย", "Network Reset"), "task_network"),
    "power": (("Ultimate Performance", "Ultimate Performance"), "task_ultimate_power"),
    "power_throttle": (("ปิด Power Throttling", "No Power Throttling"), "task_power_throttle"),
    "priority": (("ลำดับความสำคัญแอปหน้าจอ", "Foreground Priority"), "task_priority_sep"),
    "mmcss": (("MMCSS สำหรับเกม", "MMCSS Game Profile"), "task_mmcss_games"),
    "game_mode": (("เปิด Game Mode", "Enable Game Mode"), "task_game_mode"),
    "telemetry": (("ปิด Telemetry", "Disable Telemetry"), "task_telemetry"),
    "gamebar": (("ปิด Game Bar และ DVR", "Disable Game Bar & DVR"), "task_gamebar"),
    "hpet": (("ปิด HPET", "Disable HPET"), "task_hpet"),
    "net_throttle": (("ปิด Network Throttling", "No Network Throttling"), "task_net_throttle"),
    "nagle": (("ปิด Nagle (ลด Ping)", "Disable Nagle (Lower Ping)"), "task_nagle"),
    "ui_delay": (("ลดหน่วง UI / Startup", "Faster UI / Startup"), "task_ui_delay"),
    "retrim": (("TRIM สำหรับ SSD", "SSD TRIM"), "task_retrim"),
}

# ขั้นตอนที่ต้องรีสตาร์ท/ออกจากระบบเพื่อให้มีผลครบ
BOOST_NEEDS_RESTART = {"network", "power_throttle", "priority", "mmcss", "hpet", "net_throttle", "nagle"}

# โปรไฟล์: (key, ชื่อ, คำอธิบายสั้น, รายการขั้นตอนตามลำดับ)
# ไม่มีโปรไฟล์ไหนปิด Windows Defender หรือ Windows Update (ต้องสั่งเองที่หน้า Advanced เท่านั้น)
BOOST_PROFILES = [
    ("quick", ("เร็ว", "Quick"),
     ("ล้างไฟล์ขยะ แคช และ RAM ไม่แก้ค่าระบบเชิงลึก ใช้เวลาไม่นาน",
      "Cleans junk, caches and RAM without deeper system changes. Takes the least time"),
     ["restore", "junk", "update_cache", "browser", "thumbs", "dumps", "logs", "recycle", "ram"]),
    ("gaming", ("เกมมิ่ง", "Gaming"),
     ("เน้นลดหน่วงและเพิ่มความลื่นตอนเล่นเกม: แผนพลังงาน, ลำดับความสำคัญ, MMCSS, Nagle, Game Mode",
      "Focused on lower latency and smoother play: power plan, priorities, MMCSS, Nagle, Game Mode"),
     ["restore", "ram", "power", "power_throttle", "priority", "mmcss", "game_mode", "gamebar",
      "net_throttle", "nagle", "hpet"]),
    ("full", ("เต็มรูปแบบ", "Ultimate"),
     ("ทุกอย่างรวมกัน: ล้างเครื่องทั้งหมด + ปรับแต่งเกมมิ่ง + ความเป็นส่วนตัว + TRIM SSD (ไม่รวม DISM และ SFC)",
      "Everything combined: full cleanup + gaming tuning + privacy + SSD TRIM (DISM and SFC excluded)"),
     ["restore", "junk", "update_cache", "browser", "thumbs", "dumps", "logs", "recycle", "ram",
      "network", "power", "power_throttle", "priority", "mmcss", "game_mode", "telemetry", "gamebar",
      "hpet", "net_throttle", "nagle", "ui_delay", "retrim"]),
]
BOOST_PROFILE_MAP = {p[0]: p for p in BOOST_PROFILES}
BOOST_DEFAULT_PROFILE = "full"

# กลุ่มทางลัด: (ชื่อกลุ่ม TH, EN, [ (ชื่อ, คำอธิบาย TH, EN, target) ])
SHORTCUT_GROUPS = [
    ("โปรแกรมเริ่มต้นและงานเบื้องหลัง", "Startup & Background", [
        ("Startup Apps", "ปิดแอปที่เปิดเองตอนบูตเครื่อง ทำให้เปิดเครื่องไวขึ้น",
         "Turn off apps that launch at boot for a faster startup", "ms-settings:startupapps"),
        ("Task Manager", "ดูโปรเซสที่กิน CPU/RAM/Disk และแท็บ Startup apps",
         "See which processes use CPU/RAM/Disk, and the Startup apps tab", "taskmgr"),
        ("Background Apps", "ปิดแอปที่รันเบื้องหลัง (Win11: Apps > Installed apps > ... > Advanced options)",
         "Stop apps running in the background (Win11: Apps > Installed apps > ... > Advanced options)",
         "ms-settings:privacy-backgroundapps"),
        ("Services", "ปิดบริการที่ไม่ได้ใช้ (ระวัง: อย่าปิดบริการของ Windows ที่ไม่รู้จัก)",
         "Disable services you don't need (careful: leave unknown Windows services alone)", "services.msc"),
        ("System Configuration", "แท็บ Services > ติ๊ก Hide all Microsoft services แล้วปิดตัวที่ไม่ใช้",
         "Services tab > tick Hide all Microsoft services, then untick what you don't need", "msconfig"),
    ]),
    ("เอฟเฟกต์ภาพและความโปร่งใส", "Visual Effects & Transparency", [
        ("Performance Options", "เลือก Adjust for best performance เพื่อปิดแอนิเมชันและเงา",
         "Choose Adjust for best performance to turn off animations and shadows",
         "SystemPropertiesPerformance.exe"),
        ("Visual Effects (Win11)", "ปิด Transparency effects และ Animation effects",
         "Turn off Transparency effects and Animation effects", "ms-settings:easeofaccess-visualeffects"),
        ("Colors (Win10)", "ปิด Transparency effects", "Turn off Transparency effects", "ms-settings:colors"),
    ]),
    ("เกมมิ่ง", "Gaming", [
        ("Game Mode", "เปิดหรือปิด Game Mode ตามที่เหมาะกับเกมของคุณ",
         "Turn Game Mode on or off, whichever suits your games", "ms-settings:gaming-gamemode"),
        ("Xbox Game Bar", "ปิด Game Bar ที่ไม่ได้ใช้", "Turn off Game Bar if you don't use it",
         "ms-settings:gaming-gamebar"),
        ("Captures", "ปิด Background recording ที่กินทรัพยากร",
         "Turn off background recording that uses resources", "ms-settings:gaming-captures"),
        ("Graphics Settings", "เปิด Hardware-accelerated GPU scheduling และตั้งเกมเป็น High performance",
         "Enable Hardware-accelerated GPU scheduling and set games to High performance",
         "ms-settings:display-advancedgraphics"),
        ("Mouse Settings", "ปิด Enhance pointer precision (Additional mouse options > Pointer Options)",
         "Turn off Enhance pointer precision (Additional mouse options > Pointer Options)", "ms-settings:mouse"),
    ]),
    ("พลังงานและพื้นที่เก็บข้อมูล", "Power & Storage", [
        ("Power Options", "เลือกแผนพลังงาน High / Ultimate Performance",
         "Pick the High / Ultimate Performance power plan", "powercfg.cpl"),
        ("Power & Sleep", "ปรับเวลาปิดหน้าจอและ Sleep", "Adjust screen-off and sleep timers", "ms-settings:powersleep"),
        ("Storage Sense", "ตั้งให้ Windows ลบไฟล์ชั่วคราวอัตโนมัติ",
         "Let Windows delete temporary files automatically", "ms-settings:storagesense"),
        ("Disk Cleanup", "ล้างไฟล์ระบบและไฟล์ชั่วคราวที่ไม่ใช้",
         "Remove system files and temporary files you don't need", "cleanmgr"),
        ("Optimize Drives", "Defrag สำหรับ HDD / Trim สำหรับ SSD", "Defrag for HDD / Trim for SSD", "dfrgui"),
        ("Apps & Features", "ถอนโปรแกรมที่ไม่ใช้", "Uninstall programs you no longer use", "ms-settings:appsfeatures"),
    ]),
    ("ความเป็นส่วนตัว อัปเดต และแจ้งเตือน", "Privacy, Updates & Notifications", [
        ("Diagnostics & Feedback", "ปิด Optional diagnostic data และ Tailored experiences",
         "Turn off Optional diagnostic data and Tailored experiences", "ms-settings:privacy-feedback"),
        ("Notifications", "ปิดการแจ้งเตือนที่รบกวน", "Turn off distracting notifications", "ms-settings:notifications"),
        ("Windows Update", "Pause updates ระหว่างเล่นเกมสำคัญ", "Pause updates during important gaming sessions",
         "ms-settings:windowsupdate"),
        ("Delivery Optimization", "ปิดการแชร์แบนด์วิดท์อัปเดตให้เครื่องอื่น",
         "Stop sharing update bandwidth with other PCs", "ms-settings:delivery-optimization"),
        ("Resource Monitor", "ดูว่า Disk / Network ถูกใช้โดยโปรแกรมใด",
         "See which programs are using Disk / Network", "resmon"),
    ]),
]


# ======================================================================
#  Main application
# ======================================================================
class AzsieTweaker(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.configure(fg_color=BG)
        self._fit_to_screen()

        self.log_q: "queue.Queue" = queue.Queue()
        self.busy = False
        self.action_buttons = []
        self.pages = {}
        self.nav_buttons = {}
        self._i18n = []
        self.current_page = "dashboard"

        try:
            logo_path = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "azsie_logo.png")
            self.logo_img = Image.open(logo_path).convert("RGBA")
        except (OSError, ValueError):
            self.logo_img = None
        self._set_window_icon()

        self.sys_drive = os.environ.get("SystemDrive", "C:")
        self._boost_last_tick = time.time()
        self._boost_tracking = False   # ระหว่างรันขั้นตอนของ Boost: จดว่ามี log ระดับ err หรือไม่
        self._boost_err = False
        self._freed_total = 0          # ไบต์ที่ล้างได้สะสม (ใช้สรุปผลหลัง Boost)
        self._dl = self._load_dl_cache()
        self._upd_info = {"state": "idle", "tag": "", "url": "", "error": None}
        self._gpu_names = []

        self._build_ui()
        self.show_page("dashboard", animate=False)
        self.after(100, self._poll_queue)
        self.after(1500, self._tick_dashboard)
        self.after(60, self._pulse_boost)
        if AUTO_REFRESH_DOWNLOADS and dl_source():
            self.after(900, self.refresh_downloads)
        if AUTO_CHECK_UPDATE and GITHUB_REPO.strip():
            self.after(2500, lambda: self.check_update(silent=True))

        self.log(L("ยินดีต้อนรับสู่ AZSIE TWEAKER TOOL", "Welcome to AZSIE TWEAKER TOOL") + f" v{APP_VERSION}")
        if is_admin():
            self.log(L("ตรวจพบสิทธิ์ Administrator", "Administrator rights detected"), "ok")
        else:
            self.log(L("ไม่ได้รันด้วยสิทธิ์ Administrator", "Not running as Administrator"), "warn")

    # ------------------------------------------------------------------
    def _fit_to_screen(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(1080, sw - 40)
        h = min(690, sh - 110)  # เผื่อ Taskbar และแถบหัวหน้าต่าง
        x = max((sw - w) // 2, 0)
        y = max((sh - h) // 2 - 25, 0)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(min(920, w), min(540, h))

    def _set_window_icon(self):
        if self.logo_img is None:
            return
        try:
            path = os.path.join(tempfile.gettempdir(), "azsie_tweaker_icon.ico")
            self.logo_img.save(path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128)])
            self.after(300, lambda: self.iconbitmap(path))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # i18n helpers
    # ------------------------------------------------------------------
    def tr(self, widget, getter, attr="text"):
        """ผูกข้อความของ widget กับภาษา (อัปเดตอัตโนมัติเมื่อสลับภาษา)"""
        widget.configure(**{attr: getter()})
        self._i18n.append((widget, attr, getter))
        return widget

    def apply_language(self):
        for widget, attr, getter in self._i18n:
            try:
                widget.configure(**{attr: getter()})
            except Exception:
                pass
        self._refresh_page_header()
        self._update_status()
        self._render_downloads()
        self._render_update()
        self._refresh_boost_texts()

    def on_lang_change(self, value):
        global LANG
        LANG = "th" if value == "ไทย" else "en"
        data = load_settings()
        data["lang"] = LANG
        save_settings(data)
        self.apply_language()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        side_right = SIDEBAR_SIDE.lower() == "right"
        main_col, side_col = (0, 1) if side_right else (1, 0)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(main_col, weight=1)
        self.grid_columnconfigure(side_col, weight=0)

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=main_col, sticky="nsew",
                  padx=(16, 8) if side_right else (8, 16), pady=16)
        side = ctk.CTkFrame(self, width=SIDEBAR_W, fg_color=PANEL, corner_radius=18,
                            border_width=1, border_color=CARD_BORDER)
        side.grid(row=0, column=side_col, sticky="ns",
                  padx=(8, 16) if side_right else (16, 8), pady=16)
        side.grid_propagate(False)

        self._build_sidebar(side)
        self._build_main(main)

    def _build_sidebar(self, side):
        side.grid_columnconfigure(0, weight=1)
        spacer = 3 + len(NAV)
        side.grid_rowconfigure(spacer, weight=1)  # spacer

        # ปุ่มแจ้งเตือนอัปเดต (ซ่อนอยู่จนกว่าจะพบเวอร์ชันใหม่)
        self.btn_side_update = SmoothButton(
            side, text="", height=32, corner_radius=10,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#0F3D2E", hover_color="#14573F", text_color="#34D399",
            command=self.open_release,
        )
        self.btn_side_update.grid(row=spacer, column=0, padx=14, pady=(0, 8), sticky="sew")
        self.btn_side_update.grid_remove()

        if self.logo_img is not None:
            logo = ctk.CTkImage(light_image=self.logo_img, dark_image=self.logo_img, size=(70, 70))
            ctk.CTkLabel(side, text="", image=logo).grid(row=0, column=0, pady=(16, 2))
        ctk.CTkLabel(side, text="AZSIE", font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
                     text_color=ACCENT).grid(row=1, column=0)
        ctk.CTkLabel(side, text=f"TWEAKER TOOL  v{APP_VERSION}",
                     font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                     text_color=SUBTEXT).grid(row=2, column=0, pady=(0, 12))

        for i, (key, pair) in enumerate(NAV):
            btn = SmoothButton(
                side, text="", anchor="w", height=38, corner_radius=10,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                fg_color=PANEL, hover_color=NAV_HOVER, text_color=TEXT,
                command=lambda k=key: self.show_page(k),
            )
            btn.grid(row=3 + i, column=0, padx=14, pady=2, sticky="ew")
            self.tr(btn, lambda p=pair: L(*p))
            self.nav_buttons[key] = btn

        self.tr(ctk.CTkLabel(side, text="", font=ctk.CTkFont(family="Segoe UI", size=11),
                             text_color=SUBTEXT),
                lambda: L("ภาษา / Language", "Language / ภาษา")).grid(row=spacer + 1, column=0, pady=(8, 4))
        self.seg_lang = ctk.CTkSegmentedButton(
            side, values=["ไทย", "English"], command=self.on_lang_change, height=32,
            fg_color=PANEL_2, selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=PANEL_2, unselected_hover_color=NAV_HOVER, text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.seg_lang.set("ไทย" if LANG == "th" else "English")
        self.seg_lang.grid(row=spacer + 2, column=0, padx=16, sticky="ew")

        ctk.CTkLabel(side, text="Developed by AZSIE Community", font=ctk.CTkFont(family="Segoe UI", size=10),
                     text_color=SUBTEXT).grid(row=spacer + 3, column=0, pady=(10, 12))

    def _build_main(self, main):
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        # Top bar
        top = ctk.CTkFrame(main, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        self.page_title = ctk.CTkLabel(top, text="", anchor="w", text_color=TEXT,
                                       font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"))
        self.page_title.grid(row=0, column=0, sticky="w")
        self.page_sub = ctk.CTkLabel(top, text="", anchor="w", text_color=SUBTEXT,
                                     font=ctk.CTkFont(family="Segoe UI", size=12))
        self.page_sub.grid(row=1, column=0, sticky="w")
        self.btn_restore = SmoothButton(
            top, text="", width=250, height=44, corner_radius=12,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=lambda: self.run_task(("สร้างจุดคืนค่าระบบ", "Create System Restore Point"),
                                          self.task_restore_point),
        )
        self.btn_restore.grid(row=0, column=1, rowspan=2, sticky="e", padx=(10, 0))
        self.tr(self.btn_restore, lambda: L("สร้างจุดคืนค่าระบบ", "Create System Restore Point"))
        self.action_buttons.append(self.btn_restore)

        self.progress = ctk.CTkProgressBar(main, mode="indeterminate", height=5, indeterminate_speed=1.2,
                                           progress_color=ACCENT, fg_color=PANEL_2)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.progress.set(0)

        # Page host
        host = ctk.CTkFrame(main, fg_color=PANEL, corner_radius=16, border_width=1, border_color=CARD_BORDER)
        host.grid(row=2, column=0, sticky="nsew", pady=10)
        host.grid_rowconfigure(0, weight=1)
        host.grid_columnconfigure(0, weight=1)

        def make_page(key):
            page = SmoothScrollFrame(
                host, fg_color="transparent", corner_radius=12,
                scrollbar_button_color=PANEL_2, scrollbar_button_hover_color=ACCENT,
            )
            page.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
            self.pages[key] = page
            return page

        # --- Dashboard / System Info
        dash = make_page("dashboard")
        self._build_dashboard(dash)

        # --- Basic
        basic = make_page("basic")
        n = 1
        self._section(basic, ("การล้างไฟล์และแคช", "Cleanup & Caches"))
        for title, desc, method in BASIC_CLEANUP:
            self._tool_card(basic, n, title, desc, getattr(self, method))
            n += 1
        self._section(basic, ("ระบบและเครือข่าย", "System & Network"))
        for title, desc, method in BASIC_SYSTEM:
            self._tool_card(basic, n, title, desc, getattr(self, method))
            n += 1

        # --- Advanced
        adv = make_page("adv")
        n = 1
        for group_pair, tools in ADVANCED_GROUPS:
            self._section(adv, group_pair)
            for entry in tools:
                title, desc, method = entry[:3]
                opts = entry[3] if len(entry) > 3 else {}
                self._tool_card(adv, n, title, desc, getattr(self, method),
                                confirm=opts.get("confirm"), btn_label=opts.get("btn"),
                                direct=method.startswith("ask_"))
                n += 1

        # --- Shortcuts
        short = make_page("short")
        note = ctk.CTkLabel(short, text="", font=ctk.CTkFont(family="Segoe UI", size=12),
                            text_color="#FBBF24", anchor="w", justify="left", wraplength=480)
        self.tr(note, lambda: L("ทางลัดเหล่านี้แค่เปิดหน้าตั้งค่าของ Windows ให้คุณเลือกปิดเอง โปรแกรมไม่ได้แก้ค่าใด ๆ",
                                "These shortcuts only open Windows settings pages so you can switch things off yourself. "
                                "Nothing is changed by this program."))
        note.pack(fill="x", padx=14, pady=(8, 0))
        for g_th, g_en, items in SHORTCUT_GROUPS:
            self._section(short, (g_th, g_en))
            for title, d_th, d_en, target in items:
                self._shortcut_card(short, title, (d_th, d_en), target)

        # --- Boost
        boost = make_page("boost")
        self._build_boost(boost)

        # --- Info
        info_page = make_page("info")
        self._build_info(info_page)

        # --- Log
        log_frame = ctk.CTkFrame(main, fg_color=PANEL, corner_radius=16, border_width=1, border_color=CARD_BORDER)
        log_frame.grid(row=3, column=0, sticky="ew")
        log_frame.grid_columnconfigure(0, weight=1)
        bar = ctk.CTkFrame(log_frame, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        bar.grid_columnconfigure(1, weight=1)
        title = ctk.CTkLabel(bar, text="", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                             text_color=ACCENT)
        self.tr(title, lambda: L("บันทึกการทำงาน", "Log Status"))
        title.grid(row=0, column=0, sticky="w")
        self.lbl_status = ctk.CTkLabel(bar, text="", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
        self.lbl_status.grid(row=0, column=1, sticky="e", padx=10)
        clear = SmoothButton(bar, text="", width=70, height=26, corner_radius=8,
                             fg_color=PANEL_2, hover_color=NAV_HOVER, command=self.clear_log,
                             font=ctk.CTkFont(family="Segoe UI", size=11))
        self.tr(clear, lambda: L("ล้างบันทึก", "Clear"))
        clear.grid(row=0, column=3, sticky="e", padx=(6, 0))
        export = SmoothButton(bar, text="", width=110, height=26, corner_radius=8,
                              fg_color=PANEL_2, hover_color=NAV_HOVER, command=self.export_log,
                              font=ctk.CTkFont(family="Segoe UI", size=11))
        self.tr(export, lambda: L("ส่งออก log", "Export log"))
        export.grid(row=0, column=2, sticky="e")
        self.log_box = ctk.CTkTextbox(
            log_frame, height=150, fg_color="#050810", text_color=LOG_COLORS["info"],
            font=ctk.CTkFont(family="Consolas", size=12), corner_radius=10, wrap="word",
            scrollbar_button_color=PANEL_2, scrollbar_button_hover_color=ACCENT,
        )
        self.log_box.grid(row=1, column=0, padx=14, pady=(6, 14), sticky="ew")
        for level, color in LOG_COLORS.items():
            self.log_box.tag_config(level, foreground=color)
        self.log_box.configure(state="disabled")
        self._update_status()

    # ---- UI building blocks ------------------------------------------
    def _section(self, parent, pair):
        lbl = ctk.CTkLabel(parent, text="", anchor="w", text_color=ACCENT,
                           font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"))
        self.tr(lbl, lambda p=pair: L(*p).upper() if LANG == "en" else L(*p))
        lbl.pack(fill="x", padx=14, pady=(14, 2))

    def _card(self, parent, title_fn, desc_fn, btn_fn, command, index=None, btn_width=130):
        card = ctk.CTkFrame(parent, fg_color=PANEL_2, corner_radius=12, border_width=1, border_color=CARD_BORDER)
        card.pack(fill="x", padx=8, pady=4)
        card.grid_columnconfigure(1, weight=1)

        if index is not None:
            badge = ctk.CTkFrame(card, width=40, height=40, corner_radius=10, fg_color=BADGE_BG)
            badge.grid(row=0, column=0, rowspan=2, padx=(14, 0), pady=10)
            badge.grid_propagate(False)
            badge.grid_rowconfigure(0, weight=1)
            badge.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(badge, text=f"{index:02d}", text_color=ACCENT,
                         font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")).grid(row=0, column=0)
        else:
            ctk.CTkFrame(card, width=4, height=30, corner_radius=2, fg_color=ACCENT
                         ).grid(row=0, column=0, rowspan=2, padx=(14, 0), pady=10)

        t = ctk.CTkLabel(card, text="", anchor="w", text_color=TEXT,
                         font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"))
        self.tr(t, title_fn)
        t.grid(row=0, column=1, sticky="w", padx=14, pady=(10, 0))
        d = ctk.CTkLabel(card, text="", anchor="w", justify="left", wraplength=380, text_color=SUBTEXT,
                         font=ctk.CTkFont(family="Segoe UI", size=11))
        self.tr(d, desc_fn)
        d.grid(row=1, column=1, sticky="w", padx=14, pady=(0, 10))

        state = {"w": 380}

        def on_resize(e, label=d, st=state):
            w = max(e.width - 270, 200)
            if abs(w - st["w"]) > 4:
                st["w"] = w
                label.configure(wraplength=w)

        card.bind("<Configure>", on_resize)

        btn = SmoothButton(card, text="", width=btn_width, height=36, corner_radius=9,
                           font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                           fg_color=ACCENT, hover_color=ACCENT_HOVER, command=command)
        self.tr(btn, btn_fn)
        btn.grid(row=0, column=2, rowspan=2, sticky="e", padx=14, pady=8)
        return btn

    def _tool_card(self, parent, index, title, desc, func, confirm=None, btn_label=None, direct=False):
        def on_click():
            if confirm and not messagebox.askyesno(APP_NAME, L(*confirm), icon="warning"):
                return
            if direct:
                func()  # เมธอด ask_* ต้องรันบน UI thread (เปิดหน้าต่างเลือกไฟล์)
            else:
                self.run_task(title, func)

        btn = self._card(
            parent, lambda p=title: L(*p), lambda p=desc: L(*p),
            (lambda p=btn_label: L(*p)) if btn_label else (lambda: L("รัน", "RUN")),
            on_click, index=index,
        )
        self.action_buttons.append(btn)

    def _shortcut_card(self, parent, title, desc, target):
        self._card(
            parent, lambda: title, lambda p=desc: L(*p), lambda: L("เปิด", "OPEN"),
            lambda: self.quick_open(title, target), btn_width=100,
        )

    # ------------------------------------------------------------------
    # Dashboard / Info pages
    # ------------------------------------------------------------------
    def _info_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=PANEL_2, corner_radius=12, border_width=1, border_color=CARD_BORDER)
        card.pack(fill="x", padx=8, pady=4)
        ctk.CTkFrame(card, height=6, fg_color="transparent").pack()
        return card

    def _kv_row(self, card, pair, value="-"):
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=3)
        k = ctk.CTkLabel(row, text="", width=150, anchor="w", text_color=SUBTEXT,
                         font=ctk.CTkFont(family="Segoe UI", size=12))
        self.tr(k, lambda p=pair: L(*p))
        k.pack(side="left", anchor="n")
        v = ctk.CTkLabel(row, text=value, anchor="w", justify="left", wraplength=430, text_color=TEXT,
                         font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"))
        v.pack(side="left", fill="x", expand=True, padx=(8, 0))
        return v

    def _meter_card(self, parent, col, title_fn):
        card = ctk.CTkFrame(parent, fg_color=PANEL_2, corner_radius=12, border_width=1, border_color=CARD_BORDER)
        card.grid(row=0, column=col, sticky="nsew", padx=6, pady=4)
        t = ctk.CTkLabel(card, text="", anchor="w", text_color=SUBTEXT,
                         font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"))
        self.tr(t, title_fn)
        t.pack(fill="x", padx=14, pady=(12, 0))
        pct = ctk.CTkLabel(card, text="0%", anchor="w", text_color=TEXT,
                           font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"))
        pct.pack(fill="x", padx=14)
        bar = ctk.CTkProgressBar(card, height=8, progress_color=ACCENT, fg_color=BADGE_BG)
        bar.set(0)
        bar.pack(fill="x", padx=14, pady=(2, 6))
        det = ctk.CTkLabel(card, text="-", anchor="w", text_color=SUBTEXT,
                           font=ctk.CTkFont(family="Segoe UI", size=11))
        det.pack(fill="x", padx=14, pady=(0, 12))
        return {"pct": pct, "bar": bar, "det": det}

    @staticmethod
    def _load_color(p: float) -> str:
        return "#EF4444" if p >= 90 else "#F59E0B" if p >= 70 else ACCENT

    def _set_meter(self, m, pct: float, detail: str):
        pct = max(0.0, min(float(pct), 100.0))
        m["pct"].configure(text=f"{pct:.0f}%")
        m["bar"].configure(progress_color=self._load_color(pct))
        m["bar"].set(pct / 100.0)
        m["det"].configure(text=detail)

    def _build_dashboard(self, page):
        psutil.cpu_percent(interval=None)  # เรียกครั้งแรกเพื่อเริ่มวัดค่า CPU

        self._section(page, ("การใช้งานเครื่องแบบเรียลไทม์", "Live Usage"))
        meters = ctk.CTkFrame(page, fg_color="transparent")
        meters.pack(fill="x", padx=8, pady=(2, 0))
        for c in range(3):
            meters.grid_columnconfigure(c, weight=1, uniform="meter")
        self._m_cpu = self._meter_card(meters, 0, lambda: "CPU")
        self._m_ram = self._meter_card(meters, 1, lambda: "RAM")
        self._m_disk = self._meter_card(
            meters, 2, lambda: L(f"ดิสก์ ({self.sys_drive})", f"Disk ({self.sys_drive})"))

        # ---- ยอดดาวน์โหลดของแอป
        self._section(page, ("ยอดดาวน์โหลดแอป", "App Downloads"))
        dl = ctk.CTkFrame(page, fg_color=PANEL_2, corner_radius=12, border_width=1, border_color=CARD_BORDER)
        dl.pack(fill="x", padx=8, pady=4)
        dl.grid_columnconfigure(0, weight=1)
        cap = ctk.CTkLabel(dl, text="", anchor="w", text_color=SUBTEXT,
                           font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"))
        self.tr(cap, lambda: L("ดาวน์โหลดทั้งหมด", "Total downloads"))
        cap.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 0))
        self.lbl_dl_total = ctk.CTkLabel(dl, text="—", anchor="w", text_color="#34D399",
                                         font=ctk.CTkFont(family="Segoe UI", size=34, weight="bold"))
        self.lbl_dl_total.grid(row=1, column=0, sticky="w", padx=16)
        self.lbl_dl_detail = ctk.CTkLabel(dl, text="", anchor="w", justify="left", wraplength=430,
                                          text_color=SUBTEXT, font=ctk.CTkFont(family="Segoe UI", size=11))
        self.lbl_dl_detail.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 12))
        self.btn_dl = SmoothButton(dl, text="", width=120, height=36, corner_radius=9,
                                   font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                                   fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.refresh_downloads)
        self.tr(self.btn_dl, lambda: L("รีเฟรช", "REFRESH"))
        self.btn_dl.grid(row=0, column=1, rowspan=3, padx=14, pady=10)
        self._render_downloads()

        # ---- ข้อมูลระบบ
        self._section(page, ("ข้อมูลระบบ", "System Info"))
        card = self._info_card(page)
        vm = psutil.virtual_memory()
        phys = psutil.cpu_count(logical=False) or "?"
        logi = psutil.cpu_count(logical=True) or "?"
        gpus = get_gpu_names()
        self._gpu_names = gpus
        self._kv_row(card, ("ชื่อเครื่อง", "PC Name"), platform.node() or "-")
        self._kv_row(card, ("ระบบปฏิบัติการ", "Operating System"), get_os_name())
        self._kv_row(card, ("โปรเซสเซอร์", "Processor"), get_cpu_name())
        self._kv_row(card, ("แกน / เธรด", "Cores / Threads"), f"{phys} / {logi}")
        self._kv_row(card, ("การ์ดจอ", "Graphics"), "\n".join(gpus) if gpus else "-")
        self._kv_row(card, ("หน่วยความจำ", "Memory"), fmt_bytes(vm.total))
        admin_lbl = self._kv_row(card, ("สิทธิ์การใช้งาน", "Privileges"))
        self.tr(admin_lbl, lambda: "Administrator" if is_admin() else L("ผู้ใช้ทั่วไป", "Standard user"))
        self.v_uptime = self._kv_row(card, ("เปิดเครื่องมาแล้ว", "Uptime"))
        ctk.CTkFrame(card, height=6, fg_color="transparent").pack()

    def _build_info(self, page):
        self._section(page, ("เกี่ยวกับโปรแกรม", "About"))
        card = self._info_card(page)
        self._kv_row(card, ("ชื่อโปรแกรม", "Name"), APP_NAME)
        self._kv_row(card, ("เวอร์ชัน", "Version"), f"v{APP_VERSION}")
        self._kv_row(card, ("ผู้พัฒนา", "Developer"), "AZSIE Community")
        self._kv_row(card, ("รองรับ", "Supports"), "Windows 10 / 11")
        ctk.CTkFrame(card, height=6, fg_color="transparent").pack()

        self._section(page, ("อัปเดตโปรแกรม", "Updates"))
        ucard = self._info_card(page)
        self.v_latest = self._kv_row(ucard, ("เวอร์ชันล่าสุด", "Latest version"))
        self.v_upd_status = self._kv_row(ucard, ("สถานะ", "Status"))
        ub = ctk.CTkFrame(ucard, fg_color="transparent")
        ub.pack(fill="x", padx=16, pady=(6, 10))
        self.btn_upd_check = SmoothButton(
            ub, text="", width=160, height=34, corner_radius=9,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, command=lambda: self.check_update(False))
        self.tr(self.btn_upd_check, lambda: L("ตรวจสอบอัปเดต", "CHECK FOR UPDATES"))
        self.btn_upd_check.pack(side="left")
        self.btn_upd_open = SmoothButton(
            ub, text="", width=180, height=34, corner_radius=9,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=BOOST, hover_color=BOOST_HOVER, text_color="#04150E", command=self.open_release)
        self.tr(self.btn_upd_open, lambda: L("ดาวน์โหลดเวอร์ชันใหม่", "GET NEW VERSION"))
        self._render_update()

        self._section(page, ("ชุมชน", "Community"))
        dc = ctk.CTkFrame(page, fg_color=PANEL_2, corner_radius=12, border_width=1, border_color=CARD_BORDER)
        dc.pack(fill="x", padx=8, pady=4)
        dc.grid_columnconfigure(1, weight=1)
        ctk.CTkFrame(dc, width=4, height=70, corner_radius=2, fg_color=DISCORD
                     ).grid(row=0, column=0, rowspan=3, padx=(14, 0), pady=12)
        ctk.CTkLabel(dc, text="AZSIE Discord", anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
                     ).grid(row=0, column=1, sticky="w", padx=14, pady=(12, 0))
        d = ctk.CTkLabel(dc, text="", anchor="w", justify="left", wraplength=330, text_color=SUBTEXT,
                         font=ctk.CTkFont(family="Segoe UI", size=11))
        self.tr(d, lambda: L("เข้าร่วมเพื่อรับอัปเดต แจ้งปัญหา และพูดคุยกับชุมชน",
                             "Join to get updates, report problems and chat with the community"))
        d.grid(row=1, column=1, sticky="w", padx=14)
        link = ctk.CTkLabel(dc, text=DISCORD_URL, anchor="w", text_color="#8EA1FF",
                            font=ctk.CTkFont(family="Segoe UI", size=12, underline=True))
        link.grid(row=2, column=1, sticky="w", padx=14, pady=(2, 12))
        try:
            link._label.configure(cursor="hand2")  # CTkLabel ไม่รับ cursor ตรง ๆ
        except Exception:
            pass
        link.bind("<Button-1>", lambda _e: self.quick_open("Discord", DISCORD_URL))

        btns = ctk.CTkFrame(dc, fg_color="transparent")
        btns.grid(row=0, column=2, rowspan=3, padx=14, pady=10)
        join = SmoothButton(btns, text="", width=140, height=36, corner_radius=9,
                            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                            fg_color=DISCORD, hover_color=DISCORD_HOVER,
                            command=lambda: self.quick_open("Discord", DISCORD_URL))
        self.tr(join, lambda: L("เข้าร่วม Discord", "JOIN DISCORD"))
        join.pack(pady=(0, 6))
        copy = SmoothButton(btns, text="", width=140, height=30, corner_radius=9,
                            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                            fg_color=PANEL, hover_color=NAV_HOVER,
                            command=lambda: self.copy_text(DISCORD_URL))
        self.tr(copy, lambda: L("คัดลอกลิงก์", "COPY LINK"))
        copy.pack()

    # ---- Update check (GitHub Releases) --------------------------------
    def check_update(self, silent=False):
        if not GITHUB_REPO.strip():
            self._render_update()
            return
        if self._upd_info.get("state") == "loading":
            return
        self._upd_info.update(state="loading", error=None)
        self._render_update()

        def worker():
            try:
                rel = fetch_latest_release()
                self.log_q.put(("update", {"rel": rel, "error": None, "silent": silent}))
            except Exception as e:  # noqa: BLE001
                self.log_q.put(("update", {"rel": None, "error": str(e)[:120], "silent": silent}))

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_result(self, p):
        silent = p.get("silent")
        if p.get("error"):
            self._upd_info.update(state="error", error=p["error"])
            if not silent:
                self.log(L("ตรวจสอบอัปเดตไม่สำเร็จ: ", "Update check failed: ") + p["error"], "warn")
        elif not p.get("rel"):
            self._upd_info.update(state="norelease", tag="", url="", error=None)
            if not silent:
                self.log(L("ยังไม่มี Release บน GitHub", "No release published on GitHub yet"), "info")
        else:
            rel = p["rel"]
            newer = is_newer_version(rel["tag"], APP_VERSION)
            self._upd_info.update(state="new" if newer else "latest", tag=rel["tag"], url=rel["url"], error=None)
            if newer:
                self.log(L(f"พบเวอร์ชันใหม่ {rel['tag']} (ตอนนี้ใช้ v{APP_VERSION}) ไปที่หน้า Info เพื่อดาวน์โหลด",
                           f"New version {rel['tag']} available (you have v{APP_VERSION}). Open the Info page to download"),
                         "ok")
            elif not silent:
                self.log(L("คุณใช้เวอร์ชันล่าสุดแล้ว", "You are on the latest version"), "ok")
        self._render_update()

    def _render_update(self):
        u = self._upd_info
        st = u.get("state", "idle")
        tag = u.get("tag") or "-"
        if not GITHUB_REPO.strip():
            text, color = L("ยังไม่ได้ตั้งค่า GITHUB_REPO ในส่วน CONFIG ของไฟล์โปรแกรม",
                            "GITHUB_REPO is not set in the CONFIG section of the script"), SUBTEXT
        elif st == "loading":
            text, color = L("กำลังตรวจสอบ...", "Checking..."), "#FBBF24"
        elif st == "error":
            text, color = L("ตรวจสอบไม่สำเร็จ: ", "Check failed: ") + str(u.get("error") or ""), "#F87171"
        elif st == "norelease":
            text, color = L("ยังไม่มี Release บน GitHub", "No release published on GitHub yet"), SUBTEXT
        elif st == "new":
            text, color = L(f"มีเวอร์ชันใหม่ {tag}", f"New version available: {tag}"), "#34D399"
        elif st == "latest":
            text, color = L("คุณใช้เวอร์ชันล่าสุดแล้ว", "You are on the latest version"), "#34D399"
        else:
            text, color = L("ยังไม่ได้ตรวจสอบ กดปุ่มด้านล่างเพื่อตรวจสอบ",
                            "Not checked yet. Press the button below"), SUBTEXT
        try:
            self.v_latest.configure(text=tag if st in ("new", "latest") else "-")
            self.v_upd_status.configure(text=text, text_color=color)
            if st == "new":
                self.btn_upd_open.pack(side="left", padx=(8, 0))
                self.btn_side_update.configure(text=L(f"\u25CF  มีอัปเดตใหม่ {tag}", f"\u25CF  Update available {tag}"))
                self.btn_side_update.grid()
            else:
                self.btn_upd_open.pack_forget()
                self.btn_side_update.grid_remove()
        except Exception:
            pass

    def open_release(self):
        url = self._upd_info.get("url") or f"https://github.com/{GITHUB_REPO.strip().strip('/')}/releases"
        self.quick_open("GitHub Release", url)

    # ---- Export log ----------------------------------------------------
    def export_log(self):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            title=L("บันทึกไฟล์ log", "Save log file"),
            defaultextension=".txt", initialfile=f"azsie_log_{stamp}.txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            vm = psutil.virtual_memory()
            header = [
                f"{APP_NAME} v{APP_VERSION}",
                f"Date: {datetime.now():%Y-%m-%d %H:%M:%S}",
                f"OS: {get_os_name()}",
                f"CPU: {get_cpu_name()}",
                f"GPU: {', '.join(self._gpu_names) or '-'}",
                f"RAM: {fmt_bytes(vm.total)}",
                f"Administrator: {'yes' if is_admin() else 'no'}",
                "-" * 60,
            ]
            body = self.log_box.get("1.0", "end").rstrip()
            with open(path, "w", encoding="utf-8-sig") as f:  # utf-8-sig ให้ Notepad แสดงภาษาไทยถูกต้อง
                f.write("\n".join(header) + "\n" + body + "\n")
            self.log(L(f"บันทึก log แล้ว: {path}", f"Log saved: {path}"), "ok")
        except Exception as e:  # noqa: BLE001
            self.log(L(f"บันทึก log ไม่สำเร็จ: {e}", f"Could not save log: {e}"), "err")

    def copy_text(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
            self.log(L(f"คัดลอกแล้ว: {text}", f"Copied: {text}"), "ok")
        except Exception as e:  # noqa: BLE001
            self.log(L(f"คัดลอกไม่สำเร็จ: {e}", f"Could not copy: {e}"), "err")

    def _tick_dashboard(self):
        try:
            if self.current_page == "dashboard":
                cpu = psutil.cpu_percent(interval=None)
                vm = psutil.virtual_memory()
                self._set_meter(self._m_cpu, cpu,
                                f"{psutil.cpu_count(logical=True)} " + L("เธรด", "threads"))
                self._set_meter(self._m_ram, vm.percent, f"{fmt_bytes(vm.used)} / {fmt_bytes(vm.total)}")
                try:
                    du = psutil.disk_usage(self.sys_drive + "\\")
                    self._set_meter(self._m_disk, du.percent, f"{fmt_bytes(du.used)} / {fmt_bytes(du.total)}")
                except OSError:
                    pass
                secs = max(int(time.time() - psutil.boot_time()), 0)
                days, rem = divmod(secs, 86400)
                hours, rem = divmod(rem, 3600)
                mins = rem // 60
                self.v_uptime.configure(text=L(f"{days} วัน {hours} ชม. {mins} นาที",
                                               f"{days}d {hours}h {mins}m"))
        except Exception:
            pass
        self.after(1500, self._tick_dashboard)

    # ------------------------------------------------------------------
    # One-Click Boost page
    # ------------------------------------------------------------------
    def _build_boost(self, page):
        saved = load_settings().get("boost_profile")
        self.boost_profile = saved if saved in BOOST_PROFILE_MAP else BOOST_DEFAULT_PROFILE
        self._boost_ui = {"mode": "idle", "idx": 0, "total": 0, "name": ""}
        self._boost_rows = {}
        self._boost_status = {}
        self._boost_cards = {}
        self._boost_summary_data = None

        hero = ctk.CTkFrame(page, fg_color=PANEL_2, corner_radius=20, border_width=1, border_color=CARD_BORDER)
        hero.pack(fill="x", padx=8, pady=(10, 6))
        hero.grid_columnconfigure(0, weight=0, minsize=270)
        hero.grid_columnconfigure(1, weight=1)
        self.boost_hero = hero

        # ซ้าย: ปุ่มวงกลม + สถานะ / ขวา: เลือกโปรไฟล์
        left = ctk.CTkFrame(hero, fg_color="transparent")
        left.grid(row=0, column=0, sticky="n", padx=(18, 8), pady=(14, 14))
        right = ctk.CTkFrame(hero, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=(14, 14))
        right.grid_columnconfigure(0, weight=1)

        self.boost_dial = BoostDial(left, size=220, command=self.on_boost_click)
        self.boost_dial.pack()
        self.boost_status = ctk.CTkLabel(left, text="", text_color=TEXT, wraplength=250, justify="center",
                                         font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"))
        self.boost_status.pack(pady=(2, 0))
        self.boost_hint = ctk.CTkLabel(left, text="", text_color=SUBTEXT, justify="center", wraplength=250,
                                       font=ctk.CTkFont(family="Segoe UI", size=11))
        self.boost_hint.pack(pady=(2, 0))

        cards_wrap = ctk.CTkFrame(right, fg_color="transparent")
        cards_wrap.grid(row=0, column=0, sticky="nsew")
        cards_wrap.grid_columnconfigure(0, weight=1)
        self._boost_cards_wrap = cards_wrap
        for row, (key, _name, _desc, _steps) in enumerate(BOOST_PROFILES):
            self._make_profile_card(cards_wrap, row, key)
        self.boost_last = ctk.CTkLabel(cards_wrap, text="", text_color="#64748B", anchor="w",
                                       font=ctk.CTkFont(family="Segoe UI", size=11))
        self.boost_last.grid(row=len(BOOST_PROFILES), column=0, sticky="w", padx=4, pady=(8, 0))

        # ผลสรุปหลังบูสต์เสร็จ: แทนที่การ์ดโปรไฟล์ในกรอบเดียวกัน (เห็นทันทีโดยไม่ต้องเลื่อนหน้า)
        sm = ctk.CTkFrame(right, fg_color=BADGE_BG, corner_radius=14, border_width=2, border_color="#0F5C45")
        sm.grid(row=0, column=0, sticky="nsew")
        sm.grid_remove()
        sm.grid_columnconfigure((0, 1), weight=1, uniform="stat")
        self.boost_summary = sm
        self._sum_title = ctk.CTkLabel(sm, text="", anchor="w", text_color=BOOST,
                                       font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"))
        self.tr(self._sum_title, lambda: L("ผลการบูสต์", "Boost Result"))
        self._sum_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(10, 0))
        self._sum_tiles = []
        captions = (("เวลาที่ใช้", "Time"), ("พื้นที่ดิสก์ที่ล้างได้", "Disk freed"),
                    ("RAM ว่างเพิ่ม", "RAM freed"), ("ขั้นตอนที่ทำได้", "Steps done"))
        for i, cap in enumerate(captions):
            tile = ctk.CTkFrame(sm, fg_color=PANEL_2, corner_radius=10)
            tile.grid(row=1 + i // 2, column=i % 2, sticky="nsew",
                      padx=(14 if i % 2 == 0 else 4, 4 if i % 2 == 0 else 14), pady=4)
            val = ctk.CTkLabel(tile, text="-", text_color=TEXT,
                               font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"))
            val.pack(padx=8, pady=(6, 0))
            cap_lbl = ctk.CTkLabel(tile, text="", text_color=SUBTEXT, font=ctk.CTkFont(family="Segoe UI", size=11))
            self.tr(cap_lbl, lambda p=cap: L(*p))
            cap_lbl.pack(padx=8, pady=(0, 6))
            self._sum_tiles.append(val)
        self._sum_restart = ctk.CTkFrame(sm, fg_color="transparent")
        self._sum_restart.grid_columnconfigure(0, weight=1)
        self._sum_restart_lbl = ctk.CTkLabel(self._sum_restart, text="", anchor="w", justify="left",
                                             text_color="#FBBF24", wraplength=210,
                                             font=ctk.CTkFont(family="Segoe UI", size=11))
        self.tr(self._sum_restart_lbl, lambda: L("รีสตาร์ทเครื่องเพื่อให้มีผลครบ",
                                                 "Restart so everything takes effect"))
        self._sum_restart_lbl.grid(row=0, column=0, sticky="w")
        self.btn_restart = SmoothButton(
            self._sum_restart, text="", width=150, height=32, corner_radius=9,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=BOOST, hover_color=BOOST_HOVER, text_color="#04150E", command=self.restart_now)
        self.tr(self.btn_restart, lambda: L("รีสตาร์ทตอนนี้", "RESTART NOW"))
        self.btn_restart.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.btn_back = SmoothButton(
            sm, text="", height=28, corner_radius=8, font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=PANEL_2, hover_color=NAV_HOVER, command=self._boost_back)
        self.tr(self.btn_back, lambda: L("เลือกโปรไฟล์อื่น", "Choose another profile"))
        self.btn_back.grid(row=4, column=0, columnspan=2, sticky="ew", padx=14, pady=(4, 12))

        # ---- รายการขั้นตอนของโปรไฟล์ที่เลือก
        steps_card = ctk.CTkFrame(page, fg_color=PANEL_2, corner_radius=16, border_width=1, border_color=CARD_BORDER)
        steps_card.pack(fill="x", padx=8, pady=6)
        self._steps_title = ctk.CTkLabel(steps_card, text="", anchor="w", text_color=ACCENT,
                                         font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"))
        self.tr(self._steps_title, lambda: L("ขั้นตอนที่จะทำงาน", "Steps that will run"))
        self._steps_title.pack(fill="x", padx=16, pady=(12, 2))
        self.boost_steps_frame = ctk.CTkFrame(steps_card, fg_color="transparent")
        self.boost_steps_frame.pack(fill="x", padx=12, pady=(0, 12))
        self.boost_steps_frame.grid_columnconfigure((0, 1), weight=1, uniform="step")

        warn = ctk.CTkLabel(page, text="", font=ctk.CTkFont(family="Segoe UI", size=12), text_color="#FBBF24",
                            justify="center", wraplength=620)
        self.tr(warn, lambda: L("ระบบจะสร้างจุดคืนค่าระบบให้ก่อนเสมอ และไม่มีโปรไฟล์ใดปิด Windows Defender หรือ Windows Update "
                                "แนะนำให้รีสตาร์ทเครื่องหลังเสร็จสิ้น",
                                "A restore point is always created first, and no profile disables Windows Defender "
                                "or Windows Update. Restart your PC afterwards"))
        warn.pack(pady=(8, 16))

        self._render_boost_steps()
        self._apply_profile_style()
        self._update_boost_last()
        self._refresh_boost_texts()

    def _make_profile_card(self, parent, row, key):
        _k, name, desc, steps = BOOST_PROFILE_MAP[key]
        card = ctk.CTkFrame(parent, fg_color=BADGE_BG, corner_radius=14, border_width=2, border_color=CARD_BORDER)
        card.grid(row=row, column=0, sticky="ew", pady=(0 if row == 0 else 6, 0))
        card.grid_columnconfigure(0, weight=1)
        title = ctk.CTkLabel(card, text="", anchor="w", text_color=TEXT,
                             font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"))
        count = ctk.CTkLabel(card, text="", anchor="e", text_color=BOOST,
                             font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
        body = ctk.CTkLabel(card, text="", anchor="w", justify="left", text_color=SUBTEXT, wraplength=400,
                            font=ctk.CTkFont(family="Segoe UI", size=11))
        title.grid(row=0, column=0, sticky="w", padx=(14, 4), pady=(8, 0))
        count.grid(row=0, column=1, sticky="e", padx=(4, 14), pady=(8, 0))
        body.grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 9))
        self.tr(title, lambda p=name: L(*p))
        self.tr(body, lambda p=desc: L(*p))
        self.tr(count, lambda n=len(steps): L(f"{n} ขั้นตอน", f"{n} steps"))

        def on_resize(e, label=body):
            w = max(e.width - 32, 160)
            if abs(w - int(label.cget("wraplength"))) > 4:
                label.configure(wraplength=w)

        card.bind("<Configure>", on_resize)
        for w in (card, title, body, count):
            w.bind("<Button-1>", lambda _e, k=key: self._select_boost_profile(k))
            try:
                w.configure(cursor="hand2")
            except Exception:
                pass
        self._boost_cards[key] = card

    def _boost_reset_view(self):
        """กลับสู่หน้าจอพร้อมใช้งาน (ล้างผลสรุป รีเซ็ตปุ่มวงกลม)"""
        self._boost_summary_data = None
        self._boost_ui = {"mode": "idle", "idx": 0, "total": 0, "name": ""}
        self.boost_dial.state, self.boost_dial.progress, self.boost_dial.target = "idle", 0.0, 0.0

    def _boost_back(self):
        if self.busy:
            return
        self._boost_reset_view()
        self._refresh_boost_texts()

    def _show_boost_panel(self, which: str):
        if which == "summary":
            self._boost_cards_wrap.grid_remove()
            self.boost_summary.grid()
        else:
            self.boost_summary.grid_remove()
            self._boost_cards_wrap.grid()

    def _apply_profile_style(self):
        for key, card in self._boost_cards.items():
            if key == self.boost_profile:
                card.configure(border_color=BOOST, fg_color="#0E2A24")
            else:
                card.configure(border_color=CARD_BORDER, fg_color=BADGE_BG)

    def _select_boost_profile(self, key):
        if self.busy or key == self.boost_profile:
            return
        self.boost_profile = key
        data = load_settings()
        data["boost_profile"] = key
        save_settings(data)
        self._boost_reset_view()
        self._apply_profile_style()
        self._render_boost_steps()
        self._refresh_boost_texts()

    # สถานะของแต่ละขั้นตอน: (ไอคอน, สีตัวอักษร, สีพื้น)
    _STEP_STYLE = {
        "pending": ("○", SUBTEXT, BADGE_BG),
        "run": ("◉", "#34D399", "#10281F"),
        "ok": ("✓", "#34D399", BADGE_BG),
        "warn": ("!", "#FBBF24", BADGE_BG),
        "fail": ("✕", "#F87171", BADGE_BG),
    }

    def _render_boost_steps(self):
        for w in self.boost_steps_frame.winfo_children():
            w.destroy()
        self._boost_rows = {}
        self._boost_status = {}
        for i, step in enumerate(BOOST_PROFILE_MAP[self.boost_profile][3]):
            lbl = ctk.CTkLabel(self.boost_steps_frame, text="", anchor="w", height=30, corner_radius=8,
                               font=ctk.CTkFont(family="Segoe UI", size=12))
            lbl.grid(row=i // 2, column=i % 2, sticky="ew", padx=3, pady=3)
            self._boost_rows[step] = lbl
            self._set_step_row(step, "pending")

    def _set_step_row(self, step, status):
        self._boost_status[step] = status
        lbl = self._boost_rows.get(step)
        if lbl is None:
            return
        icon, fg, bg = self._STEP_STYLE[status]
        lbl.configure(text=f"  {icon}   {L(*BOOST_STEPS[step][0])}", text_color=fg, fg_color=bg)

    def _refresh_boost_texts(self):
        """อัปเดตข้อความของหน้า Boost ตามภาษาและสถานะปัจจุบัน"""
        ui = self._boost_ui
        prof = BOOST_PROFILE_MAP[self.boost_profile]
        if ui["mode"] == "run":
            self.boost_status.configure(
                text=L(f"ขั้นตอน {ui['idx'] + 1}/{ui['total']}: {ui['name']}",
                       f"Step {ui['idx'] + 1}/{ui['total']}: {ui['name']}"), text_color="#34D399")
            self.boost_hint.configure(text=L("กำลังทำงาน กรุณาอย่าปิดโปรแกรม", "Working, please keep the app open"))
        elif ui["mode"] == "done":
            self.boost_status.configure(text=L("บูสต์เสร็จสมบูรณ์", "Boost complete"), text_color="#34D399")
            self.boost_hint.configure(text=L("กดปุ่มวงกลมอีกครั้งเพื่อรันซ้ำ หรือเลือกโปรไฟล์อื่นทางขวา",
                                             "Press the dial to run again, or choose another profile"))
        else:
            self.boost_status.configure(
                text=L(f"พร้อมบูสต์ ({len(prof[3])} ขั้นตอน)", f"Ready to boost ({len(prof[3])} steps)"),
                text_color=TEXT)
            self.boost_hint.configure(text=L("กดปุ่มวงกลมเพื่อเริ่มบูสต์", "Press the dial to start boosting"))
        for step in self._boost_rows:
            self._set_step_row(step, self._boost_status.get(step, "pending"))
        self._render_boost_summary()
        self._update_boost_last()

    def _update_boost_last(self):
        last = load_settings().get("boost_last") or {}
        try:
            pname = BOOST_PROFILE_MAP.get(last.get("profile"), BOOST_PROFILE_MAP[BOOST_DEFAULT_PROFILE])[1]
            self.boost_last.configure(text=L(
                f"ครั้งล่าสุด: {last['time']} · โปรไฟล์ {pname[0]} · ล้างได้ {fmt_bytes(last['freed'])}",
                f"Last run: {last['time']} · {pname[1]} profile · freed {fmt_bytes(last['freed'])}"))
        except (KeyError, TypeError, ValueError):
            self.boost_last.configure(text=L("ยังไม่เคยรัน", "Not run yet"))

    @staticmethod
    def _fmt_elapsed(sec: float) -> str:
        sec = int(sec)
        return f"{sec} s" if sec < 60 else f"{sec // 60}m {sec % 60:02d}s"

    def _render_boost_summary(self):
        p = self._boost_summary_data
        if not p or self._boost_ui["mode"] != "done":
            self._show_boost_panel("cards")
            return
        vals = (self._fmt_elapsed(p["elapsed"]), fmt_bytes(p["freed"]), fmt_bytes(p["ram"]),
                f"{p['ok'] + p['warn']}/{p['total']}")
        for lbl, v in zip(self._sum_tiles, vals):
            lbl.configure(text=v)
        self._sum_title.configure(text_color="#FBBF24" if (p["fail"] or p["warn"]) else BOOST)
        if p["restart"]:
            self._sum_restart.grid(row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=(4, 2))
        else:
            self._sum_restart.grid_remove()
        self._show_boost_panel("summary")

    def _on_boost_event(self, p):
        ev = p.get("ev")
        if ev == "start":
            self._boost_summary_data = None
            for step in self._boost_rows:
                self._set_step_row(step, "pending")
            self._boost_ui = {"mode": "run", "idx": 0, "total": p["total"], "name": ""}
            self.boost_dial.begin()
            self._render_boost_summary()
            try:
                self.pages["boost"]._parent_canvas.yview_moveto(0)
            except Exception:
                pass
        elif ev == "step":
            idx, total, status = p["index"], self._boost_ui["total"] or 1, p["status"]
            self._set_step_row(p["key"], status)
            if status == "run":
                self._boost_ui.update(mode="run", idx=idx, name=p["name"])
                self.boost_dial.set_target((idx + 0.5) / total)
            else:
                self.boost_dial.set_target((idx + 1) / total)
            self._refresh_boost_texts()
        elif ev == "done":
            self._boost_ui["mode"] = "done"
            self._boost_summary_data = p
            self.boost_dial.finish()
            data = load_settings()
            data["boost_last"] = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "profile": p["profile"],
                                  "freed": int(p["freed"]), "ok": p["ok"] + p["warn"], "total": p["total"]}
            save_settings(data)
            self._refresh_boost_texts()

    def restart_now(self):
        if not messagebox.askyesno(
            APP_NAME,
            L("รีสตาร์ทเครื่องตอนนี้หรือไม่?\n\nกรุณาบันทึกงานที่เปิดอยู่ก่อน เครื่องจะรีสตาร์ทใน 15 วินาที",
              "Restart the PC now?\n\nSave your work first. The PC will restart in 15 seconds."),
        ):
            return
        try:
            subprocess.Popen(["shutdown", "/r", "/t", "15", "/c", "AZSIE Tweaker"], creationflags=CREATE_NO_WINDOW)
            self.log(L("สั่งรีสตาร์ทใน 15 วินาที (ยกเลิกได้ด้วยคำสั่ง shutdown /a)",
                       "Restart scheduled in 15 seconds (cancel with the command shutdown /a)"), "warn")
        except OSError as e:
            self.log(L(f"สั่งรีสตาร์ทไม่สำเร็จ: {e}", f"Could not schedule the restart: {e}"), "err")

    def _pulse_boost(self):
        # ขับแอนิเมชันของปุ่มวงกลม (ทำงานเฉพาะตอนเปิดหน้า Boost)
        now = time.time()
        dt = now - self._boost_last_tick
        self._boost_last_tick = now
        try:
            if self.current_page == "boost" and self.winfo_viewable():
                self.boost_dial.tick(dt)
        except Exception:
            pass
        self.after(45, self._pulse_boost)

    # ---- Download counter --------------------------------------------
    def _load_dl_cache(self):
        state = {"total": None, "releases": [], "time": None, "error": None, "loading": False}
        try:
            c = load_settings().get("dl_cache") or {}
            if c.get("src") == dl_source() and isinstance(c.get("total"), int):
                state["total"] = c["total"]
                state["releases"] = [(str(t), int(n)) for t, n in c.get("releases", [])]
                state["time"] = c.get("time")
        except Exception:
            pass
        return state

    def _render_downloads(self):
        d = self._dl
        if not dl_source():
            self.lbl_dl_total.configure(text="—")
            self.lbl_dl_detail.configure(text=L(
                "ยังไม่ได้ตั้งค่าแหล่งข้อมูล: ใส่ GITHUB_REPO (เช่น owner/repo) หรือ DOWNLOAD_STATS_URL "
                "ในส่วน CONFIG ด้านบนของไฟล์โปรแกรม",
                "No data source set: fill in GITHUB_REPO (e.g. owner/repo) or DOWNLOAD_STATS_URL "
                "in the CONFIG section at the top of the script"))
            return
        total = d.get("total")
        self.lbl_dl_total.configure(text=f"{total:,}" if total is not None else "—")
        lines = []
        if d.get("loading"):
            lines.append(L("กำลังดึงข้อมูล...", "Fetching..."))
        elif d.get("error"):
            lines.append(L("ดึงข้อมูลไม่สำเร็จ: ", "Fetch failed: ") + str(d["error"]))
        for tag, cnt in d.get("releases", [])[:5]:
            lines.append(f"{tag}: {cnt:,}")
        if d.get("time"):
            lines.append(L("อัปเดตล่าสุด: ", "Last updated: ") + str(d["time"]))
        if not lines:
            lines.append(L("กดรีเฟรชเพื่อดึงยอดดาวน์โหลด", "Press Refresh to fetch the download count"))
        self.lbl_dl_detail.configure(text="\n".join(lines))

    def refresh_downloads(self):
        if not dl_source():
            self._render_downloads()
            return
        if self._dl.get("loading"):
            return
        self._dl["loading"] = True
        self._dl["error"] = None
        self._render_downloads()

        def worker():
            try:
                total, releases = fetch_download_stats()
                self.log_q.put(("dl", {
                    "total": total, "releases": releases, "error": None, "loading": False,
                    "time": datetime.now().strftime("%d/%m/%Y %H:%M"),
                }))
            except Exception as e:  # noqa: BLE001
                self.log_q.put(("dl", {"error": str(e)[:120], "loading": False}))

        threading.Thread(target=worker, daemon=True).start()

    # ---- Fullscreen Optimizations (เลือกไฟล์ .exe บน UI thread) ----------
    def ask_fso_disable(self):
        self._ask_fso(True)

    def ask_fso_enable(self):
        self._ask_fso(False)

    def _ask_fso(self, disable: bool):
        path = filedialog.askopenfilename(
            title=L("เลือกไฟล์ .exe ของเกม", "Choose the game's .exe"),
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
        )
        if not path:
            return
        name = os.path.basename(path)
        if disable:
            pair = (f"ปิด Fullscreen Optimizations: {name}", f"Disable Fullscreen Optimizations: {name}")
        else:
            pair = (f"คืนค่า Fullscreen Optimizations: {name}", f"Restore Fullscreen Optimizations: {name}")
        self.run_task(pair, lambda: self._fso_apply(path, disable))

    # ---- GPU Preference (เลือกไฟล์ .exe บน UI thread) ------------------
    def ask_gpu_high(self):
        self._ask_gpu(2)

    def ask_gpu_saving(self):
        self._ask_gpu(1)

    def ask_gpu_reset(self):
        self._ask_gpu(0)

    def _ask_gpu(self, mode: int):
        path = filedialog.askopenfilename(
            title=L("เลือกไฟล์ .exe ของเกม", "Choose the game's .exe"),
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
        )
        if not path:
            return
        name = os.path.basename(path)
        pairs = {
            2: (f"ตั้งการ์ดจอ High Performance: {name}", f"Set GPU to High Performance: {name}"),
            1: (f"ตั้งการ์ดจอ Power Saving: {name}", f"Set GPU to Power Saving: {name}"),
            0: (f"คืนค่าการ์ดจอ: {name}", f"Reset GPU preference: {name}"),
        }
        self.run_task(pairs[mode], lambda: self._gpu_apply(path, mode))

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def _refresh_page_header(self):
        pair = dict(NAV)[self.current_page]
        self.page_title.configure(text=L(*pair))
        self.page_sub.configure(text=L(*PAGE_SUB[self.current_page]))

    def show_page(self, key, animate=True):
        self.current_page = key
        for k, page in self.pages.items():
            if k == key:
                page.grid()
            else:
                page.grid_remove()
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.set_palette(ACCENT, ACCENT_HOVER)
            else:
                btn.set_palette(PANEL, NAV_HOVER)
        self._refresh_page_header()

    def quick_open(self, title, target):
        def worker():
            try:
                open_target(target)
                self.log(L(f"เปิด: {title}", f"Opened: {title}"), "ok")
            except Exception as e:  # noqa: BLE001
                self.log(L(f"เปิด {title} ไม่สำเร็จ: {e}", f"Could not open {title}: {e}"), "err")
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Logging (thread-safe through queue)
    # ------------------------------------------------------------------
    def log(self, text: str, level: str = "info"):
        if level == "err" and self._boost_tracking:
            self._boost_err = True
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_q.put(("log", (stamp, LOG_PREFIX.get(level, "") + text, level)))

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.log_q.get_nowait()
                if kind == "log":
                    stamp, text, level = payload
                    self.log_box.configure(state="normal")
                    self.log_box.insert("end", f"[{stamp}] ", "dim")
                    self.log_box.insert("end", text + "\n", level)
                    self.log_box.see("end")
                    self.log_box.configure(state="disabled")
                elif kind == "done":
                    self._set_busy(False)
                elif kind == "update":
                    self._on_update_result(payload)
                elif kind == "boost":
                    self._on_boost_event(payload)
                elif kind == "dl":
                    self._dl.update(payload)
                    if payload.get("total") is not None:
                        data = load_settings()
                        data["dl_cache"] = {
                            "src": dl_source(), "total": payload["total"],
                            "releases": [list(r) for r in payload.get("releases", [])],
                            "time": payload.get("time"),
                        }
                        save_settings(data)
                    self._render_downloads()
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _update_status(self):
        if self.busy:
            self.lbl_status.configure(text=L("กำลังทำงาน", "WORKING"), text_color="#FBBF24")
        else:
            self.lbl_status.configure(text=L("พร้อมใช้งาน", "READY"), text_color="#34D399")

    def _set_busy(self, busy: bool):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in self.action_buttons:
            b.configure(state=state)
        if not busy:  # ปุ่มวงกลมเข้าสู่โหมดทำงานจากอีเวนต์ "start" ของ Boost เท่านั้น (ไม่ใช่งานอื่น)
            self.boost_dial.set_busy(False)
        if busy:
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.set(0)
        self._update_status()

    # ------------------------------------------------------------------
    # Task runner (ทุกงานรันใน threading.Thread)
    # ------------------------------------------------------------------
    def run_task(self, name_pair, func):
        if self.busy:
            self.log(L("มีงานกำลังทำอยู่ กรุณารอให้เสร็จก่อน", "A task is already running, please wait"), "warn")
            return
        self._set_busy(True)

        def worker():
            name = L(*name_pair)
            self.log(L(f"เริ่ม: {name}", f"Started: {name}"), "run")
            try:
                func()
                self.log(L(f"เสร็จสิ้น: {name}", f"Finished: {name}"), "ok")
            except Exception as e:  # noqa: BLE001
                self.log(L(f"ผิดพลาดใน {name}: {e}", f"Error in {name}: {e}"), "err")
            finally:
                self.log_q.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()

    def on_boost_click(self):
        if self.busy:
            self.log(L("มีงานกำลังทำอยู่ กรุณารอให้เสร็จก่อน", "A task is already running, please wait"), "warn")
            return
        key, name, desc, steps = BOOST_PROFILE_MAP[self.boost_profile]
        names = [L(*BOOST_STEPS[k][0]) for k in steps]
        lines = [", ".join(names[i:i + 3]) for i in range(0, len(names), 3)]
        listing = "\n".join("- " + ln for ln in lines)
        if messagebox.askyesno(
            APP_NAME,
            L(f"รัน ONE-CLICK BOOST โปรไฟล์ \"{name[0]}\" ({len(steps)} ขั้นตอน) หรือไม่?\n\n{L(*desc)}\n\n"
              f"{listing}\n\nระบบจะสร้างจุดคืนค่าระบบให้ก่อนเริ่ม",
              f"Run ONE-CLICK BOOST with the \"{name[1]}\" profile ({len(steps)} steps)?\n\n{L(*desc)}\n\n"
              f"{listing}\n\nA restore point will be created first"),
        ):
            self.run_task((f"ONE-CLICK BOOST ({name[0]})", f"ONE-CLICK BOOST ({name[1]})"),
                          lambda k=key: self.task_boost(k))

    # ------------------------------------------------------------------
    # Command helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _decode(data: bytes) -> str:
        if not data:
            return ""
        if data.count(b"\x00") > len(data) // 4:  # เช่น sfc ให้ผลลัพธ์เป็น UTF-16
            return data.decode("utf-16-le", errors="ignore").replace("\ufeff", "")
        for enc in ("oem", "utf-8", "cp874"):
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode("utf-8", errors="replace")

    def run_cmd(self, args, show_output=True, timeout=600):
        """รันคำสั่งแบบไม่เปิดหน้าต่าง cmd แล้วคืนค่า (returncode, output)"""
        self.log(args if isinstance(args, str) else " ".join(args), "cmd")
        proc = subprocess.run(
            args, capture_output=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW, shell=isinstance(args, str),
        )
        out = (self._decode(proc.stdout) + "\n" + self._decode(proc.stderr)).strip()
        if show_output and out:
            for line in out.splitlines():
                line = line.strip()
                if line and "% complete" not in line.lower():
                    self.log(line, "dim")
        return proc.returncode, out

    def run_ps(self, script: str, timeout=900):
        return self.run_cmd(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Cleaning helpers
    # ------------------------------------------------------------------
    def _clean_dir(self, path: str, verbose=True) -> int:
        """ลบเนื้อหาในโฟลเดอร์ (ไม่ลบตัวโฟลเดอร์) คืนค่าจำนวนไบต์ที่ล้างได้"""
        if not path or not os.path.isdir(path):
            if verbose:
                self.log(L(f"ข้าม (ไม่พบโฟลเดอร์): {path}", f"Skipped (folder not found): {path}"), "dim")
            return 0
        if verbose:
            self.log(L(f"กำลังล้าง: {path}", f"Cleaning: {path}"))
        before = dir_size(path)
        skipped = 0
        try:
            entries = list(os.scandir(path))
        except OSError as e:
            if verbose:
                self.log(L(f"อ่านโฟลเดอร์ไม่ได้: {e}", f"Cannot read folder: {e}"), "warn")
            return 0
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    shutil.rmtree(entry.path, ignore_errors=True)
                    if os.path.exists(entry.path):
                        skipped += 1
                else:
                    os.unlink(entry.path)
            except OSError:
                skipped += 1
        freed = max(before - dir_size(path), 0)
        self._freed_total += freed
        if verbose:
            self.log(L(f"ลบแล้ว {fmt_bytes(freed)} (ข้าม {skipped} รายการที่ถูกใช้งานอยู่)",
                       f"Freed {fmt_bytes(freed)} (skipped {skipped} items in use)"), "ok")
        return freed

    def _clean_glob(self, pattern: str):
        """ลบไฟล์ตาม pattern คืนค่า (ไบต์ที่ล้างได้, จำนวนไฟล์ที่ลบ, จำนวนที่ข้าม)"""
        freed = deleted = skipped = 0
        for f in glob.glob(pattern):
            try:
                size = os.path.getsize(f)
                os.unlink(f)
                freed += size
                deleted += 1
            except OSError:
                skipped += 1
        self._freed_total += freed
        return freed, deleted, skipped

    # ------------------------------------------------------------------
    # TASKS - Basic
    # ------------------------------------------------------------------
    def task_restore_point(self):
        script = (
            '$ErrorActionPreference="Stop"; '
            'Enable-ComputerRestore -Drive "$env:SystemDrive\\"; '
            f'Checkpoint-Computer -Description "{RESTORE_POINT_NAME}" -RestorePointType "MODIFY_SETTINGS"; '
            'Write-Output "Restore point created."'
        )
        code, _ = self.run_ps(script)
        if code == 0:
            self.log(L("สร้างจุดคืนค่าระบบสำเร็จ", "System restore point created"), "ok")
        else:
            self.log(L("สร้างจุดคืนค่าระบบไม่สำเร็จ (ตรวจสอบว่าเปิด System Protection ไว้ "
                       "และ Windows จำกัดการสร้าง 1 จุดต่อ 24 ชั่วโมง)",
                       "Could not create a restore point (make sure System Protection is on; "
                       "Windows allows one restore point per 24 hours by default)"), "warn")

    def task_clean_junk(self):
        win = os.environ.get("SystemRoot", r"C:\Windows")
        paths = []
        for p in (os.environ.get("TEMP"), os.environ.get("TMP"),
                  os.path.join(win, "Temp"), os.path.join(win, "Prefetch")):
            if p and os.path.normcase(p) not in [os.path.normcase(x) for x in paths]:
                paths.append(p)
        total = 0
        for p in paths:
            total += self._clean_dir(p)
        self.log(L(f"รวมล้างไฟล์ขยะได้ {fmt_bytes(total)}", f"Total junk removed: {fmt_bytes(total)}"), "ok")

    def task_update_cache(self):
        win = os.environ.get("SystemRoot", r"C:\Windows")
        services = ("wuauserv", "bits")
        was_running = []
        for s in services:
            try:
                if psutil.win_service_get(s).status() == "running":
                    was_running.append(s)
            except Exception:
                pass
        for s in was_running:
            self.run_cmd(["net", "stop", s, "/y"])
        try:
            self._clean_dir(os.path.join(win, "SoftwareDistribution", "Download"))
        finally:
            for s in was_running:
                self.run_cmd(["net", "start", s])

    def task_browser_cache(self):
        local = os.environ.get("LOCALAPPDATA", "")
        if not local:
            self.log(L("ไม่พบโฟลเดอร์ LOCALAPPDATA", "LOCALAPPDATA folder not found"), "warn")
            return
        chromium = (
            ("Google Chrome", r"Google\Chrome\User Data"),
            ("Microsoft Edge", r"Microsoft\Edge\User Data"),
            ("Brave", r"BraveSoftware\Brave-Browser\User Data"),
        )
        cache_dirs = ("Cache", "Code Cache", "GPUCache")
        grand = 0
        for name, rel in chromium:
            root = os.path.join(local, rel)
            if not os.path.isdir(root):
                continue
            freed = 0
            for prof in os.listdir(root):
                if prof == "Default" or prof.startswith("Profile "):
                    for sub in cache_dirs:
                        freed += self._clean_dir(os.path.join(root, prof, sub), verbose=False)
            self.log(L(f"{name}: ล้างได้ {fmt_bytes(freed)}", f"{name}: freed {fmt_bytes(freed)}"), "ok")
            grand += freed
        ff_root = os.path.join(local, "Mozilla", "Firefox", "Profiles")
        if os.path.isdir(ff_root):
            freed = 0
            for prof in os.listdir(ff_root):
                freed += self._clean_dir(os.path.join(ff_root, prof, "cache2"), verbose=False)
            self.log(L(f"Firefox: ล้างได้ {fmt_bytes(freed)}", f"Firefox: freed {fmt_bytes(freed)}"), "ok")
            grand += freed
        self.log(L(f"รวมล้างแคชเบราว์เซอร์ได้ {fmt_bytes(grand)} (ไฟล์ที่เบราว์เซอร์เปิดอยู่จะถูกข้าม)",
                   f"Total browser cache removed: {fmt_bytes(grand)} (files in use are skipped)"), "ok")

    def task_thumbnails(self):
        local = os.environ.get("LOCALAPPDATA", "")
        explorer = os.path.join(local, "Microsoft", "Windows", "Explorer")
        total = deleted = skipped = 0
        for pattern in (os.path.join(explorer, "thumbcache_*.db"),
                        os.path.join(explorer, "iconcache_*.db"),
                        os.path.join(local, "IconCache.db")):
            f, d, s = self._clean_glob(pattern)
            total += f
            deleted += d
            skipped += s
        self.log(L(f"ลบ {deleted} ไฟล์ ({fmt_bytes(total)}) ข้าม {skipped} ไฟล์ที่ Explorer ใช้งานอยู่",
                   f"Deleted {deleted} files ({fmt_bytes(total)}), skipped {skipped} in use by Explorer"), "ok")
        self.log(L("Windows จะสร้างแคชใหม่เองเมื่อเปิดโฟลเดอร์ครั้งถัดไป",
                   "Windows will rebuild the cache next time you open folders"), "info")

    def task_crash_dumps(self):
        win = os.environ.get("SystemRoot", r"C:\Windows")
        pd = os.environ.get("ProgramData", r"C:\ProgramData")
        local = os.environ.get("LOCALAPPDATA", "")
        wer = os.path.join(pd, "Microsoft", "Windows", "WER")
        total = 0
        for d in (os.path.join(win, "Minidump"),
                  os.path.join(local, "CrashDumps"),
                  os.path.join(wer, "ReportQueue"),
                  os.path.join(wer, "ReportArchive"),
                  os.path.join(wer, "Temp")):
            total += self._clean_dir(d)
        for pattern in (os.path.join(win, "MEMORY.DMP"), os.path.join(win, "LiveKernelReports", "*.dmp")):
            f, d, _s = self._clean_glob(pattern)
            if d:
                self.log(L(f"ลบไฟล์ dump {d} ไฟล์ ({fmt_bytes(f)})", f"Deleted {d} dump file(s) ({fmt_bytes(f)})"), "ok")
            total += f
        self.log(L(f"รวมล้างได้ {fmt_bytes(total)}", f"Total removed: {fmt_bytes(total)}"), "ok")

    def task_recycle_bin(self):
        flags = SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        res = _shell32.SHEmptyRecycleBinW(None, None, flags) & 0xFFFFFFFF
        if res == 0:
            self.log(L("ล้างถังขยะเรียบร้อย", "Recycle Bin emptied"), "ok")
        elif res == 0x8000FFFF:
            self.log(L("ถังขยะว่างอยู่แล้ว", "Recycle Bin is already empty"), "info")
        else:
            self.log(L(f"ล้างถังขยะไม่สำเร็จ (รหัส 0x{res:08X})", f"Could not empty Recycle Bin (code 0x{res:08X})"), "err")

    def task_optimize_ram(self):
        before = psutil.virtual_memory().available
        self.log(L(f"RAM ว่างก่อนทำงาน: {fmt_bytes(before)}", f"Free RAM before: {fmt_bytes(before)}"))

        cleared = 0
        for pid in psutil.pids():
            if pid in (0, 4):
                continue
            h = _k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION, False, pid)
            if not h:
                continue
            try:
                if _psapi.EmptyWorkingSet(h):
                    cleared += 1
            finally:
                _k32.CloseHandle(h)
        self.log(L(f"เคลียร์ Memory Working Set แล้ว {cleared} โปรเซส",
                   f"Trimmed the Working Set of {cleared} processes"), "ok")

        ok1 = enable_privilege("SeProfileSingleProcessPrivilege")
        enable_privilege("SeIncreaseQuotaPrivilege")
        if not ok1:
            self.log(L("เปิดสิทธิ์ SeProfileSingleProcessPrivilege ไม่สำเร็จ",
                       "Could not enable SeProfileSingleProcessPrivilege"), "warn")
        s1 = nt_memory_command(MEMORY_FLUSH_MODIFIED_LIST)
        s2 = nt_memory_command(MEMORY_PURGE_STANDBY_LIST)
        self.log("Flush Modified Page List: " + ("OK" if s1 == 0 else f"failed (0x{s1 & 0xFFFFFFFF:08X})"),
                 "ok" if s1 == 0 else "warn")
        self.log("Purge Standby List: " + ("OK" if s2 == 0 else f"failed (0x{s2 & 0xFFFFFFFF:08X})"),
                 "ok" if s2 == 0 else "warn")

        after = psutil.virtual_memory().available
        self.log(L(f"RAM ว่างหลังทำงาน: {fmt_bytes(after)} (เปลี่ยนแปลง {fmt_bytes(after - before)})",
                   f"Free RAM after: {fmt_bytes(after)} (change {fmt_bytes(after - before)})"), "ok")

    def task_network(self):
        self.run_cmd(["ipconfig", "/flushdns"])
        self.run_cmd(["netsh", "winsock", "reset"])
        self.run_cmd(["netsh", "int", "ip", "reset"])
        self.log(L("กรุณารีสตาร์ทเครื่องเพื่อให้การรีเซ็ตเครือข่ายมีผล",
                   "Please restart your PC for the network reset to take effect"), "warn")

    def task_dism(self):
        self.log(L("กำลังรัน DISM อาจใช้เวลาหลายนาที กรุณารอ...", "Running DISM, this may take several minutes..."))
        code, _ = self.run_cmd(["dism", "/online", "/cleanup-image", "/startcomponentcleanup"], timeout=3600)
        if code != 0:
            self.log(L(f"DISM จบด้วยรหัส {code}", f"DISM exited with code {code}"), "warn")

    def task_sfc(self):
        self.log(L("กำลังสแกนไฟล์ระบบ อาจใช้เวลา 10-30 นาที กรุณารอ...",
                   "Scanning system files, this may take 10-30 minutes..."))
        code, _ = self.run_cmd(["sfc", "/scannow"], timeout=7200)
        if code != 0:
            self.log(L(f"SFC จบด้วยรหัส {code}", f"SFC exited with code {code}"), "warn")

    # ------------------------------------------------------------------
    # TASKS - Advanced
    # ------------------------------------------------------------------
    def task_ultimate_power(self):
        ultimate_template = "e9a42b02-d5df-448d-aa00-03f14749eb61"
        guid_re = re.compile(r"([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})")
        guid = None

        _, listing = self.run_cmd(["powercfg", "/list"], show_output=False)
        for line in listing.splitlines():
            if "ultimate performance" in line.lower() or "ประสิทธิภาพสูงสุด" in line:
                m = guid_re.search(line)
                if m:
                    guid = m.group(1)
                    self.log(L(f"พบแผน Ultimate Performance อยู่แล้ว: {guid}",
                               f"Ultimate Performance plan already exists: {guid}"))
                    break

        if not guid:
            code, out = self.run_cmd(["powercfg", "-duplicatescheme", ultimate_template])
            m = guid_re.search(out)
            if code != 0 or not m:
                self.log(L("สร้างแผน Ultimate Performance ไม่สำเร็จ (บางเครื่อง เช่น Laptop แบบ Modern Standby อาจไม่รองรับ)",
                           "Could not create the Ultimate Performance plan (some PCs, e.g. Modern Standby laptops, "
                           "do not support it)"), "err")
                return
            guid = m.group(1)

        code, _ = self.run_cmd(["powercfg", "/setactive", guid])
        if code == 0:
            self.log(L("เปิดใช้งานแผนพลังงาน Ultimate Performance แล้ว", "Ultimate Performance power plan is now active"), "ok")
        else:
            self.log(L("เปลี่ยนแผนพลังงานไม่สำเร็จ", "Could not switch the power plan"), "err")

    def task_telemetry(self):
        for svc in ("DiagTrack", "dmwappushservice"):
            self.log(L(f"จัดการบริการ: {svc}", f"Handling service: {svc}"))
            code, _ = self.run_cmd(["sc", "query", svc], show_output=False)
            if code != 0:
                self.log(L(f"ไม่พบบริการ {svc} ในเครื่องนี้ - ข้าม", f"Service {svc} not found on this PC - skipped"), "dim")
                continue
            self.run_cmd(["sc", "stop", svc])
            self.run_cmd(["sc", "config", svc, "start=", "disabled"])
        self.log(L("ปิดบริการ Telemetry เรียบร้อย", "Telemetry services disabled"), "ok")

    @staticmethod
    def _set_dword(root, path, name, value):
        with winreg.CreateKeyEx(root, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)

    def task_gamebar(self):
        items = [
            (winreg.HKEY_CURRENT_USER, r"System\GameConfigStore", "GameDVR_Enabled", 0, "HKCU\\...\\GameConfigStore\\GameDVR_Enabled"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0, "HKCU\\...\\GameDVR\\AppCaptureEnabled"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "UseNexusForGameBarEnabled", 0, "HKCU\\...\\GameBar\\UseNexusForGameBarEnabled"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\GameDVR", "AllowGameDVR", 0, "HKLM\\...\\Policies\\GameDVR\\AllowGameDVR"),
        ]
        for root, path, name, value, label in items:
            try:
                self._set_dword(root, path, name, value)
                self.log(f"{label} = {value}", "dim")
            except OSError as e:
                self.log(L(f"ตั้งค่า {label} ไม่สำเร็จ: {e}", f"Could not set {label}: {e}"), "err")
        self.log(L("ปิด Xbox Game Bar และ Game DVR แล้ว (อาจต้องออก/เข้าสู่ระบบใหม่เพื่อให้มีผลเต็มที่)",
                   "Xbox Game Bar and Game DVR disabled (sign out and in again for full effect)"), "ok")

    def task_hpet(self):
        code, _ = self.run_cmd(["bcdedit", "/deletevalue", "useplatformclock"])
        if code == 0:
            self.log(L("ลบค่า useplatformclock แล้ว (ต้องรีสตาร์ทเครื่อง)",
                       "useplatformclock removed (restart required)"), "ok")
        else:
            self.log(L("ไม่พบค่า useplatformclock ใน BCD แปลว่า Windows ไม่ได้บังคับใช้ HPET อยู่แล้ว",
                       "useplatformclock is not set in BCD, so Windows is not forcing HPET already"), "info")

    # ------------------------------------------------------------------
    # TASKS - Advanced tweaks (registry helpers)
    # ------------------------------------------------------------------
    @staticmethod
    def _reg_set(root, path, name, value):
        if isinstance(value, bytes):
            kind = winreg.REG_BINARY
        elif isinstance(value, str):
            kind = winreg.REG_SZ
        else:
            kind = winreg.REG_DWORD
        with winreg.CreateKeyEx(root, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
            winreg.SetValueEx(key, name, 0, kind, value)

    @staticmethod
    def _reg_del(root, path, name) -> bool:
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
                winreg.DeleteValue(key, name)
            return True
        except OSError:
            return False

    def _reg_apply(self, items):
        ok = fail = 0
        for root, path, name, value in items:
            try:
                self._reg_set(root, path, name, value)
                ok += 1
            except OSError as e:
                fail += 1
                self.log(L(f"ตั้งค่า {name} ไม่สำเร็จ: {e}", f"Could not set {name}: {e}"), "warn")
        return ok, fail

    def _log_applied(self, ok: int, fail: int):
        if fail:
            self.log(L(f"ตั้งค่าสำเร็จ {ok} รายการ ข้าม {fail} รายการที่ Windows ไม่อนุญาต",
                       f"Applied {ok} setting(s), {fail} blocked by Windows"), "warn")
        else:
            self.log(L(f"ตั้งค่าสำเร็จ {ok} รายการ", f"Applied {ok} setting(s)"), "ok")

    # ------------------------------------------------------------------
    # TASKS - Advanced tweaks
    # ------------------------------------------------------------------
    def task_mouse_accel(self):
        items = [(HKCU, r"Control Panel\Mouse", n, "0")
                 for n in ("MouseSpeed", "MouseThreshold1", "MouseThreshold2")]
        ok, fail = self._reg_apply(items)
        self._log_applied(ok, fail)
        try:  # ใช้ค่าใหม่ทันทีโดยไม่ต้องออกจากระบบ
            params = (ctypes.c_int * 3)(0, 0, 0)
            applied = bool(ctypes.windll.user32.SystemParametersInfoW(
                SPI_SETMOUSE, 0, params, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE))
        except Exception:
            applied = False
        if applied:
            self.log(L("ปิด Mouse Acceleration แล้ว และมีผลทันที", "Mouse acceleration disabled and applied now"), "ok")
        else:
            self.log(L("บันทึกค่าแล้ว แต่ต้องออกจากระบบแล้วเข้าใหม่เพื่อให้มีผล",
                       "Saved, but sign out and in again for it to take effect"), "warn")
        self.log(L("เคล็ดลับ: ตั้งความเร็วตัวชี้ที่ 6/11 (ค่าเริ่มต้น) จะได้การเคลื่อนที่ 1:1 พอดี",
                   "Tip: keep pointer speed at 6/11 (default) for an exact 1:1 movement"), "info")

    def task_net_throttle(self):
        path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
        ok, fail = self._reg_apply([
            (HKLM, path, "NetworkThrottlingIndex", 0xFFFFFFFF),  # ปิด Network Throttling
            (HKLM, path, "SystemResponsiveness", 0),
        ])
        self._log_applied(ok, fail)
        if ok:
            self.log(L("ปิด Network Throttling และตั้ง SystemResponsiveness = 0 แล้ว (ต้องรีสตาร์ทเครื่อง)",
                       "Network Throttling disabled and SystemResponsiveness set to 0 (restart required)"), "ok")

    def task_hags(self):
        try:
            build = int(str(reg_read(HKLM, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "CurrentBuild", "0")))
        except ValueError:
            build = 0
        if build and build < 19041:
            self.log(L("HAGS ต้องใช้ Windows 10 เวอร์ชัน 2004 (build 19041) ขึ้นไป - ข้าม",
                       "HAGS needs Windows 10 version 2004 (build 19041) or newer - skipped"), "warn")
            return
        ok, fail = self._reg_apply([(HKLM, r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode", 2)])
        self._log_applied(ok, fail)
        if ok:
            self.log(L("ตั้ง HwSchMode = 2 แล้ว ต้องรีสตาร์ทเครื่อง (ถ้าการ์ดจอ/ไดรเวอร์ไม่รองรับ ค่านี้จะไม่มีผล)",
                       "HwSchMode set to 2. Restart required (has no effect if the GPU/driver does not support it)"),
                     "ok")

    def task_visual_fx(self):
        adv = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
        best_perf_mask = bytes([0x90, 0x12, 0x03, 0x80, 0x10, 0x00, 0x00, 0x00])
        ok, fail = self._reg_apply([
            (HKCU, r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects", "VisualFXSetting", 2),
            (HKCU, r"Control Panel\Desktop", "UserPreferencesMask", best_perf_mask),
            (HKCU, r"Control Panel\Desktop", "FontSmoothing", "2"),  # คงฟอนต์ให้เรียบ ไม่ให้ตัวอักษรหยัก
            (HKCU, r"Control Panel\Desktop\WindowMetrics", "MinAnimate", "0"),
            (HKCU, adv, "TaskbarAnimations", 0),
            (HKCU, adv, "ListviewShadow", 0),
            (HKCU, r"Software\Microsoft\Windows\DWM", "EnableAeroPeek", 0),
            (HKCU, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency", 0),
        ])
        self._log_applied(ok, fail)
        try:
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 0x2, 3000, None)
        except Exception:
            pass
        self.log(L("ตั้ง Visual Effects เป็น Best Performance แล้ว (ออกจากระบบแล้วเข้าใหม่เพื่อให้มีผลครบ)",
                   "Visual Effects set to Best Performance (sign out and in again for full effect)"), "ok")

    def task_start_clean(self):
        cdm = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
        adv = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
        items = []
        for name in ("ContentDeliveryAllowed", "OemPreInstalledAppsEnabled", "PreInstalledAppsEnabled",
                     "PreInstalledAppsEverEnabled", "SilentInstalledAppsEnabled", "SoftLandingEnabled",
                     "SystemPaneSuggestionsEnabled", "SubscribedContentEnabled",
                     "SubscribedContent-310093Enabled", "SubscribedContent-338387Enabled",
                     "SubscribedContent-338388Enabled", "SubscribedContent-338389Enabled",
                     "SubscribedContent-338393Enabled", "SubscribedContent-353694Enabled",
                     "SubscribedContent-353696Enabled", "SubscribedContent-353698Enabled",
                     "SubscribedContent-88000326Enabled"):
            items.append((HKCU, cdm, name, 0))
        items += [
            (HKCU, adv, "Start_IrisRecommendations", 0),       # ส่วน Recommended ใน Start (Win11)
            (HKCU, adv, "Start_AccountNotifications", 0),
            (HKCU, adv, "ShowSyncProviderNotifications", 0),   # โฆษณาใน File Explorer
            (HKCU, adv, "TaskbarDa", 0),                       # ปุ่ม Widgets (Win11)
            (HKCU, r"Software\Microsoft\Windows\CurrentVersion\Feeds", "ShellFeedsTaskbarViewMode", 2),
            (HKCU, r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0),
            (HKLM, r"SOFTWARE\Policies\Microsoft\Dsh", "AllowNewsAndInterests", 0),
            (HKLM, r"SOFTWARE\Policies\Microsoft\Windows\Windows Feeds", "EnableFeeds", 0),
            (HKLM, r"SOFTWARE\Policies\Microsoft\Windows\CloudContent", "DisableWindowsConsumerFeatures", 1),
            (HKLM, r"SOFTWARE\Policies\Microsoft\Windows\CloudContent", "DisableThirdPartySuggestions", 1),
        ]
        ok, fail = self._reg_apply(items)
        self._log_applied(ok, fail)
        if fail:
            self.log(L("Windows 11 รุ่นใหม่ล็อกบางค่า (เช่นปุ่ม Widgets) ถ้ายังเห็นอยู่ให้ปิดที่ "
                       "Settings > Personalization > Taskbar",
                       "Newer Windows 11 builds lock some values (e.g. the Widgets button). If it is still "
                       "shown, switch it off in Settings > Personalization > Taskbar"), "info")
        self.log(L("ปิด Widgets คำแนะนำ และโฆษณาใน Start Menu แล้ว (ออกจากระบบแล้วเข้าใหม่เพื่อให้มีผลครบ)",
                   "Widgets, suggestions and Start Menu ads turned off (sign out and in for full effect)"), "ok")

    # ---- Fullscreen Optimizations (ต่อเกม) -----------------------------
    def _fso_apply(self, exe: str, disable: bool):
        layers = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
        flag = "DISABLEDXMAXIMIZEDWINDOWEDMODE"
        exe = os.path.normpath(exe)
        if not (os.path.isfile(exe) and exe.lower().endswith(".exe")):
            self.log(L(f"ไม่ใช่ไฟล์ .exe ที่ใช้งานได้: {exe}", f"Not a valid .exe file: {exe}"), "err")
            return
        flags = []
        try:
            with winreg.OpenKey(HKCU, layers, 0, winreg.KEY_READ) as key:
                cur = winreg.QueryValueEx(key, exe)[0]
                flags = [f for f in str(cur).split() if f != "~"]  # เก็บแฟลกอื่นของเกมไว้ เช่น RUNASADMIN
        except OSError:
            pass
        if disable:
            if flag not in flags:
                flags.append(flag)
        else:
            flags = [f for f in flags if f != flag]
        with winreg.CreateKeyEx(HKCU, layers, 0, winreg.KEY_SET_VALUE) as key:
            if flags:
                winreg.SetValueEx(key, exe, 0, winreg.REG_SZ, "~ " + " ".join(flags))
            else:
                try:
                    winreg.DeleteValue(key, exe)
                except OSError:
                    pass
        name = os.path.basename(exe)
        if disable:
            self.log(L(f"ปิด Fullscreen Optimizations ให้ {name} แล้ว (เปิดเกมใหม่เพื่อให้มีผล)",
                       f"Fullscreen Optimizations disabled for {name} (relaunch the game)"), "ok")
        else:
            self.log(L(f"คืนค่า Fullscreen Optimizations ให้ {name} แล้ว",
                       f"Fullscreen Optimizations restored for {name}"), "ok")

    # ---- GPU Preference (ต่อเกม) ---------------------------------------
    def _gpu_apply(self, exe: str, mode: int):
        """mode: 2 = High performance, 1 = Power saving, 0 = ให้ Windows ตัดสินใจ (ลบค่า)"""
        key_path = r"Software\Microsoft\DirectX\UserGpuPreferences"
        exe = os.path.normpath(exe)
        if not (os.path.isfile(exe) and exe.lower().endswith(".exe")):
            self.log(L(f"ไม่ใช่ไฟล์ .exe ที่ใช้งานได้: {exe}", f"Not a valid .exe file: {exe}"), "err")
            return
        name = os.path.basename(exe)

        # เก็บตัวเลือกอื่นของเกมไว้ เช่น SwapEffectUpgradeEnable=1;
        others = []
        try:
            with winreg.OpenKey(HKCU, key_path, 0, winreg.KEY_READ) as key:
                cur = str(winreg.QueryValueEx(key, exe)[0])
                others = [p for p in cur.split(";") if p.strip() and not p.strip().startswith("GpuPreference")]
        except OSError:
            pass

        parts = list(others)
        if mode in (1, 2):
            parts.insert(0, f"GpuPreference={mode}")
        value = "".join(p.strip() + ";" for p in parts)

        with winreg.CreateKeyEx(HKCU, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if value:
                winreg.SetValueEx(key, exe, 0, winreg.REG_SZ, value)
            else:
                try:
                    winreg.DeleteValue(key, exe)
                except OSError:
                    pass

        if mode == 2:
            self.log(L(f"ตั้ง {name} ให้ใช้การ์ดจอ High performance แล้ว (เปิดเกมใหม่เพื่อให้มีผล)",
                       f"{name} set to the High performance GPU (relaunch the game)"), "ok")
        elif mode == 1:
            self.log(L(f"ตั้ง {name} ให้ใช้การ์ดจอ Power saving แล้ว (เปิดเกมใหม่เพื่อให้มีผล)",
                       f"{name} set to the Power saving GPU (relaunch the game)"), "ok")
        else:
            self.log(L(f"คืนค่าการ์ดจอของ {name} แล้ว (ให้ Windows เลือกเอง)",
                       f"GPU preference for {name} reset (Windows decides)"), "ok")

    # ---- Windows Defender ----------------------------------------------
    DEFENDER_POL = r"SOFTWARE\Policies\Microsoft\Windows Defender"
    DEFENDER_RTP = DEFENDER_POL + r"\Real-Time Protection"
    DEFENDER_VALUES = (
        ("", "DisableAntiSpyware"), ("", "DisableAntiVirus"),
        ("rtp", "DisableRealtimeMonitoring"), ("rtp", "DisableBehaviorMonitoring"),
        ("rtp", "DisableOnAccessProtection"), ("rtp", "DisableScanOnRealtimeEnable"),
        ("rtp", "DisableIOAVProtection"),
    )

    def task_defender_off(self):
        tp = reg_read(HKLM, r"SOFTWARE\Microsoft\Windows Defender\Features", "TamperProtection")
        if tp in (1, 5):
            self.log(L("Tamper Protection เปิดอยู่ ต้องปิดที่ Windows Security > Virus & threat protection "
                       "settings > Tamper Protection ก่อน ไม่เช่นนั้น Windows จะเปลี่ยนค่ากลับ",
                       "Tamper Protection is ON. Turn it off in Windows Security > Virus & threat protection "
                       "settings > Tamper Protection first, otherwise Windows reverts the change"), "warn")
        code, _ = self.run_ps(
            "Set-MpPreference -DisableRealtimeMonitoring $true -DisableBehaviorMonitoring $true "
            "-DisableIOAVProtection $true -DisableScriptScanning $true -DisableBlockAtFirstSeen $true "
            "-MAPSReporting 0 -SubmitSamplesConsent 2")
        if code != 0:
            self.log(L("Set-MpPreference ไม่สำเร็จ (อาจเพราะ Tamper Protection หรือมีโปรแกรมป้องกันอื่นติดตั้งอยู่)",
                       "Set-MpPreference failed (Tamper Protection or another antivirus may be in the way)"), "warn")
        items = [(HKLM, self.DEFENDER_RTP if where == "rtp" else self.DEFENDER_POL, name, 1)
                 for where, name in self.DEFENDER_VALUES]
        ok, fail = self._reg_apply(items)
        self._log_applied(ok, fail)
        self.log(L("ตั้งนโยบายปิด Windows Defender แล้ว (ต้องรีสตาร์ทเครื่องเพื่อให้มีผลเต็มที่)",
                   "Windows Defender policies set to off (restart for full effect)"), "ok")

    def task_defender_on(self):
        self.run_ps(
            "Set-MpPreference -DisableRealtimeMonitoring $false -DisableBehaviorMonitoring $false "
            "-DisableIOAVProtection $false -DisableScriptScanning $false -DisableBlockAtFirstSeen $false "
            "-MAPSReporting 2 -SubmitSamplesConsent 1")
        removed = 0
        for where, name in self.DEFENDER_VALUES:
            if self._reg_del(HKLM, self.DEFENDER_RTP if where == "rtp" else self.DEFENDER_POL, name):
                removed += 1
        self.log(L(f"ลบนโยบายที่ปิด Defender {removed} รายการ และเปิดการป้องกันกลับแล้ว (รีสตาร์ทเครื่อง 1 ครั้ง)",
                   f"Removed {removed} Defender-off polic(ies) and re-enabled protection (restart once)"), "ok")

    # ---- Windows Update ------------------------------------------------
    WU_POLICY = r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
    WU_SERVICES = ("wuauserv", "UsoSvc", "WaaSMedicSvc")
    WU_TASKS = (
        r"\Microsoft\Windows\WindowsUpdate\Scheduled Start",
        r"\Microsoft\Windows\UpdateOrchestrator\Schedule Scan",
        r"\Microsoft\Windows\UpdateOrchestrator\USO_UxBroker",
        r"\Microsoft\Windows\WaaSMedic\PerformRemediation",
    )

    def task_wupdate_off(self):
        ok, fail = self._reg_apply([
            (HKLM, self.WU_POLICY, "NoAutoUpdate", 1),
            (HKLM, self.WU_POLICY, "AUOptions", 1),
        ])
        self._log_applied(ok, fail)
        blocked = []
        for svc in self.WU_SERVICES:
            code, _ = self.run_cmd(["sc", "query", svc], show_output=False)
            if code != 0:
                continue
            self.run_cmd(["sc", "stop", svc])
            code, _ = self.run_cmd(["sc", "config", svc, "start=", "disabled"])
            if code != 0:
                blocked.append(svc)
        for task in self.WU_TASKS:
            self.run_cmd(["schtasks", "/Change", "/TN", task, "/Disable"])
        if blocked:
            self.log(L(f"Windows ป้องกันบริการ {', '.join(blocked)} ไว้จึงปิดไม่ได้ "
                       "แต่นโยบายห้ามอัปเดตอัตโนมัติยังมีผลอยู่",
                       f"Windows protects the service(s) {', '.join(blocked)} so they could not be disabled, "
                       "but the no-auto-update policy is still in effect"), "warn")
        self.log(L("ปิด Windows Update ถาวรแล้ว (กด \"เปิด Windows Update กลับ\" เมื่อต้องการอัปเดต)",
                   "Windows Update disabled (use \"Re-enable Windows Update\" when you want updates)"), "ok")

    def task_wupdate_on(self):
        removed = 0
        for name in ("NoAutoUpdate", "AUOptions"):
            if self._reg_del(HKLM, self.WU_POLICY, name):
                removed += 1
        for svc, start in (("wuauserv", "demand"), ("UsoSvc", "delayed-auto"), ("WaaSMedicSvc", "demand")):
            code, _ = self.run_cmd(["sc", "query", svc], show_output=False)
            if code != 0:
                continue
            self.run_cmd(["sc", "config", svc, "start=", start])
        for task in self.WU_TASKS:
            self.run_cmd(["schtasks", "/Change", "/TN", task, "/Enable"])
        self.run_cmd(["sc", "start", "wuauserv"])
        self.log(L(f"ลบนโยบายห้ามอัปเดต {removed} รายการ และคืนค่าบริการแล้ว (รีสตาร์ทเครื่อง 1 ครั้ง)",
                   f"Removed {removed} update-blocking polic(ies) and restored the services (restart once)"), "ok")

    # ------------------------------------------------------------------
    # TASKS - เพิ่มเติม (ล้างแคช / ปรับแต่งประสิทธิภาพ / ความเป็นส่วนตัว)
    # ------------------------------------------------------------------
    def task_shader_cache(self):
        local = os.environ.get("LOCALAPPDATA", "")
        pdata = os.environ.get("ProgramData", r"C:\ProgramData")
        dirs = [os.path.join(pdata, "NVIDIA Corporation", "NV_Cache")]
        if local:
            dirs += [os.path.join(local, p) for p in (
                "D3DSCache", r"NVIDIA\DXCache", r"NVIDIA\GLCache", r"AMD\DxCache", r"AMD\DxcCache",
                r"AMD\GLCache", r"Intel\ShaderCache")]
        total = found = 0
        for d in dirs:
            if os.path.isdir(d):
                found += 1
                total += self._clean_dir(d)
        if not found:
            self.log(L("ไม่พบแคช Shader ในเครื่องนี้", "No shader caches found on this PC"), "info")
            return
        self.log(L(f"รวมล้างแคช Shader ได้ {fmt_bytes(total)}", f"Total shader cache removed: {fmt_bytes(total)}"), "ok")
        self.log(L("เกมจะสร้างแคชใหม่เองตอนเปิดครั้งถัดไป อาจกระตุกเล็กน้อยในครั้งแรก",
                   "Games rebuild their caches on next launch; the first run may stutter slightly"), "info")

    def task_sys_logs(self):
        win = os.environ.get("SystemRoot", r"C:\Windows")
        total = 0
        for d in (os.path.join(win, "Logs", "CBS"), os.path.join(win, "Logs", "DISM"),
                  os.path.join(win, "Logs", "WindowsUpdate"),
                  os.path.join(win, "SoftwareDistribution", "DeliveryOptimization"),
                  os.path.join(win, "ServiceProfiles", "NetworkService", "AppData", "Local", "Microsoft",
                               "Windows", "DeliveryOptimization", "Cache")):
            if os.path.isdir(d):
                total += self._clean_dir(d)
        self.log(L(f"รวมล้างบันทึกระบบและแคชได้ {fmt_bytes(total)}", f"Total logs and cache removed: {fmt_bytes(total)}"), "ok")

    def task_retrim(self):
        script = (
            '$ErrorActionPreference="Stop"; '
            '$dl=$env:SystemDrive.TrimEnd(":"); '
            '$m=(Get-Partition -DriveLetter $dl | Get-Disk | Get-PhysicalDisk | Select-Object -First 1).MediaType; '
            'if($m -eq "SSD"){Optimize-Volume -DriveLetter $dl -ReTrim; Write-Output "TRIM_OK"} '
            'else {Write-Output "NOT_SSD"}'
        )
        code, out = self.run_ps(script, timeout=1800)
        if "TRIM_OK" in out:
            self.log(L("สั่ง TRIM ไดรฟ์ระบบ (SSD) เรียบร้อย", "TRIM completed on the system drive (SSD)"), "ok")
        elif "NOT_SSD" in out:
            self.log(L("ไดรฟ์ระบบไม่ใช่ SSD (หรือตรวจชนิดไม่ได้) - ข้าม TRIM", "System drive is not an SSD (or its type is unknown) - TRIM skipped"), "info")
        else:
            self.log(L("สั่ง TRIM ไม่สำเร็จ", "Could not run TRIM"), "err")

    def task_power_throttle(self):
        ok, fail = self._reg_apply([(HKLM, r"SYSTEM\CurrentControlSet\Control\Power\PowerThrottling",
                                     "PowerThrottlingOff", 1)])
        self._log_applied(ok, fail)
        if ok:
            self.log(L("ปิด Power Throttling แล้ว (ต้องรีสตาร์ทเครื่อง)", "Power Throttling disabled (restart required)"), "ok")

    def task_priority_sep(self):
        ok, fail = self._reg_apply([(HKLM, r"SYSTEM\CurrentControlSet\Control\PriorityControl",
                                     "Win32PrioritySeparation", 0x26)])
        self._log_applied(ok, fail)
        if ok:
            self.log(L("ตั้ง Win32PrioritySeparation = 0x26 แล้ว (ต้องรีสตาร์ทเครื่อง)",
                       "Win32PrioritySeparation set to 0x26 (restart required)"), "ok")

    def task_mmcss_games(self):
        path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games"
        ok, fail = self._reg_apply([
            (HKLM, path, "GPU Priority", 8),
            (HKLM, path, "Priority", 6),
            (HKLM, path, "Scheduling Category", "High"),
            (HKLM, path, "SFIO Priority", "High"),
        ])
        self._log_applied(ok, fail)
        if ok:
            self.log(L("ปรับโปรไฟล์ MMCSS สำหรับเกมแล้ว (ต้องรีสตาร์ทเครื่อง)", "MMCSS game profile tuned (restart required)"), "ok")

    def task_nagle(self):
        base = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
        try:
            with winreg.OpenKey(HKLM, base, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                guids = [winreg.EnumKey(k, i) for i in range(winreg.QueryInfoKey(k)[0])]
        except OSError as e:
            self.log(L(f"อ่านรายการการ์ดเครือข่ายไม่ได้: {e}", f"Could not read the network adapter list: {e}"), "err")
            return

        def has_ip(path):
            for name in ("DhcpIPAddress", "IPAddress"):
                v = reg_read(HKLM, path, name)
                for x in (v if isinstance(v, (list, tuple)) else [v]):
                    if x and x != "0.0.0.0":
                        return True
            return False

        items, adapters = [], 0
        for g in guids:
            path = base + "\\" + g
            if has_ip(path):
                adapters += 1
                items += [(HKLM, path, "TcpAckFrequency", 1), (HKLM, path, "TCPNoDelay", 1)]
        if not adapters:
            self.log(L("ไม่พบการ์ดเครือข่ายที่มี IP - ข้าม", "No network adapter with an IP address found - skipped"), "warn")
            return
        ok, fail = self._reg_apply(items)
        self._log_applied(ok, fail)
        self.log(L(f"ปิด Nagle Algorithm กับการ์ดเครือข่าย {adapters} ตัวแล้ว (ต้องรีสตาร์ทเครื่อง)",
                   f"Nagle's algorithm disabled on {adapters} adapter(s) (restart required)"), "ok")

    def task_game_mode(self):
        path = r"Software\Microsoft\GameBar"
        ok, fail = self._reg_apply([(HKCU, path, "AutoGameModeEnabled", 1), (HKCU, path, "AllowAutoGameMode", 1)])
        self._log_applied(ok, fail)
        if ok:
            self.log(L("เปิด Game Mode แล้ว", "Game Mode enabled"), "ok")

    def task_ui_delay(self):
        ok, fail = self._reg_apply([
            (HKCU, r"Control Panel\Desktop", "MenuShowDelay", "0"),
            (HKCU, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize", "StartupDelayInMSec", 0),
        ])
        self._log_applied(ok, fail)
        if ok:
            self.log(L("ลดความหน่วงเมนูและ Startup delay แล้ว (ออกจากระบบแล้วเข้าใหม่เพื่อให้มีผล)",
                       "Menu delay and startup delay reduced (sign out and in for it to apply)"), "ok")

    def task_fast_shutdown(self):
        ok, fail = self._reg_apply([
            (HKLM, r"SYSTEM\CurrentControlSet\Control", "WaitToKillServiceTimeout", "3000"),
            (HKCU, r"Control Panel\Desktop", "WaitToKillAppTimeout", "5000"),
            (HKCU, r"Control Panel\Desktop", "HungAppTimeout", "3000"),
        ])
        self._log_applied(ok, fail)
        if ok:
            self.log(L("ลดเวลารอตอนปิดเครื่องแล้ว", "Shutdown wait times reduced"), "ok")

    def task_hibernate_off(self):
        code, _ = self.run_cmd(["powercfg", "/h", "off"])
        if code == 0:
            self.log(L("ปิด Hibernate และลบ hiberfil.sys แล้ว", "Hibernate disabled and hiberfil.sys removed"), "ok")
        else:
            self.log(L("ปิด Hibernate ไม่สำเร็จ", "Could not disable Hibernate"), "err")

    def task_hibernate_on(self):
        code, _ = self.run_cmd(["powercfg", "/h", "on"])
        if code == 0:
            self.log(L("เปิด Hibernate กลับแล้ว", "Hibernate re-enabled"), "ok")
        else:
            self.log(L("เปิด Hibernate ไม่สำเร็จ (เครื่องบางรุ่นไม่รองรับ)", "Could not enable Hibernate (not supported on some PCs)"), "err")

    def task_activity_history(self):
        pol = r"SOFTWARE\Policies\Microsoft\Windows\System"
        ok, fail = self._reg_apply([
            (HKLM, pol, "EnableActivityFeed", 0),
            (HKLM, pol, "PublishUserActivities", 0),
            (HKLM, pol, "UploadUserActivities", 0),
            (HKCU, r"Control Panel\International\User Profile", "HttpAcceptLanguageOptOut", 1),
        ])
        self._log_applied(ok, fail)
        if ok:
            self.log(L("ปิด Activity History และการติดตามภาษาแล้ว", "Activity History and language tracking turned off"), "ok")

    def task_bing_search(self):
        ok, fail = self._reg_apply([
            (HKCU, r"Software\Microsoft\Windows\CurrentVersion\Search", "BingSearchEnabled", 0),
            (HKCU, r"Software\Microsoft\Windows\CurrentVersion\Search", "CortanaConsent", 0),
            (HKCU, r"Software\Policies\Microsoft\Windows\Explorer", "DisableSearchBoxSuggestions", 1),
        ])
        self._log_applied(ok, fail)
        if ok:
            self.log(L("ปิดการค้นหาเว็บใน Start Menu แล้ว (ออกจากระบบแล้วเข้าใหม่เพื่อให้มีผล)",
                       "Web search in the Start Menu turned off (sign out and in for it to apply)"), "ok")

    def task_bg_apps(self):
        ok, fail = self._reg_apply([
            (HKCU, r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", "GlobalUserDisabled", 1),
            (HKCU, r"Software\Microsoft\Windows\CurrentVersion\Search", "BackgroundAppGlobalToggle", 0),
        ])
        self._log_applied(ok, fail)
        if ok:
            self.log(L("ปิดแอป Store ที่รันเบื้องหลังแล้ว", "Store apps running in the background turned off"), "ok")

    # ------------------------------------------------------------------
    # One-click boost
    # ------------------------------------------------------------------
    def _boost_post(self, **payload):
        self.log_q.put(("boost", payload))

    def task_boost(self, profile: str = BOOST_DEFAULT_PROFILE):
        key, pname, _desc, step_keys = BOOST_PROFILE_MAP.get(profile) or BOOST_PROFILE_MAP[BOOST_DEFAULT_PROFILE]
        total = len(step_keys)
        t0 = time.time()
        self._freed_total = 0
        try:
            ram_before = psutil.virtual_memory().available
        except Exception:  # noqa: BLE001
            ram_before = 0
        counts = {"ok": 0, "warn": 0, "fail": 0}
        needs_restart = False
        self.log(L(f"โปรไฟล์: {pname[0]} ({total} ขั้นตอน)", f"Profile: {pname[1]} ({total} steps)"), "run")
        self._boost_post(ev="start", total=total)
        for i, step in enumerate(step_keys):
            pair, method = BOOST_STEPS[step]
            name = L(*pair)
            self.log(f"-------- [{i + 1}/{total}] {name} --------", "run")
            self._boost_post(ev="step", index=i, key=step, status="run", name=name)
            self._boost_err = False
            self._boost_tracking = True
            status = "ok"
            try:
                getattr(self, method)()
                if self._boost_err:
                    status = "warn"
            except Exception as e:  # noqa: BLE001
                status = "fail"
                self.log(L(f"ขั้นตอน {name} ผิดพลาด: {e}", f"Step {name} failed: {e}"), "err")
            finally:
                self._boost_tracking = False
            counts[status] += 1
            if step in BOOST_NEEDS_RESTART and status != "fail":
                needs_restart = True
            self._boost_post(ev="step", index=i, key=step, status=status, name=name)
        try:
            ram_gain = max(psutil.virtual_memory().available - ram_before, 0)
        except Exception:  # noqa: BLE001
            ram_gain = 0
        elapsed = time.time() - t0
        self._boost_post(ev="done", profile=key, total=total, ok=counts["ok"], warn=counts["warn"],
                         fail=counts["fail"], elapsed=elapsed, freed=self._freed_total, ram=ram_gain,
                         restart=needs_restart)
        summary = L(f"สำเร็จ {counts['ok'] + counts['warn']}/{total} ขั้นตอน ใช้เวลา {int(elapsed)} วินาที "
                    f"ล้างได้ {fmt_bytes(self._freed_total)}",
                    f"{counts['ok'] + counts['warn']}/{total} steps done in {int(elapsed)} s, "
                    f"freed {fmt_bytes(self._freed_total)}")
        self.log(L("บูสต์เสร็จสมบูรณ์: ", "Boost complete: ") + summary, "ok" if not counts["fail"] else "warn")
        if needs_restart:
            self.log(L("กรุณารีสตาร์ทเครื่อง 1 ครั้งเพื่อให้การปรับแต่งมีผลครบ",
                       "Please restart your PC once so every change takes full effect"), "warn")

    def task_ultimate_boost(self):
        self.task_boost("full")


# ======================================================================
if __name__ == "__main__":
    ensure_admin()
    app = AzsieTweaker()
    app.mainloop()
