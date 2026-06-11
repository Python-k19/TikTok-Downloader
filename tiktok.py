"""
TikTok Downloader — Production Edition
Автономный, с автоматической установкой зависимостей
"""

import customtkinter as ctk
import requests
import threading
import os
import sys
import platform
import re
import subprocess
import json
import stat
from pathlib import Path
from datetime import datetime, timedelta

# ═══════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════

if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
    IS_FROZEN = True
else:
    APP_DIR = Path(__file__).parent.resolve()
    IS_FROZEN = False

DOWNLOAD_DIR = APP_DIR / "tiktok_downloads"
BIN_DIR = APP_DIR / "bin"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
BIN_DIR.mkdir(parents=True, exist_ok=True)

APP_VERSION = "1.2.0"
APP_NAME = "TikTokDownloader"

# GitHub для автообновления
GITHUB_USER = "Python-k19"
GITHUB_REPO = "tiktok-downloader"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
REMOTE_CONFIG_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/config.json"

# yt-dlp release
YTDLP_RELEASES_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"

DEFAULT_APIS = [
    {"name": "TikWM",    "url": "https://www.tikwm.com/api/", "method": "POST", "priority": 1},
    {"name": "TikWM v2", "url": "https://tikwm.com/api/",     "method": "POST", "priority": 2},
]

COLORS = {
    "bg_dark":  "#0a0a14", "bg_card":  "#1a1a2e", "bg_input": "#151528",
    "accent":   "#ff0050", "accent2":  "#00f2ea", "text":     "#ffffff",
    "text_dim": "#8b8ba7", "border":   "#2a2a4a", "success":  "#00f2ea",
    "warning":  "#ffb800", "danger":   "#ff0050",
}

SYSTEM = platform.system()


# ═══════════════════════════════════════════════════════
# МЕНЕДЖЕР ЗАВИСИМОСТЕЙ (yt-dlp)
# ═══════════════════════════════════════════════════════

class DependencyManager:
    """Автономная установка и обновление yt-dlp"""
    
    CACHE_FILE = BIN_DIR / ".deps_cache.json"
    
    def __init__(self, log_callback=None):
        self.log = log_callback or (lambda *a, **kw: None)
        self.ytdlp_path = BIN_DIR / ("yt-dlp.exe" if SYSTEM == "Windows" else "yt-dlp")
        self._cache = self._load_cache()
    
    def _load_cache(self):
        try:
            if self.CACHE_FILE.exists():
                return json.loads(self.CACHE_FILE.read_text(encoding="utf-8"))
        except:
            pass
        return {}
    
    def _save_cache(self):
        try:
            self.CACHE_FILE.write_text(
                json.dumps(self._cache, indent=2), encoding="utf-8"
            )
        except:
            pass
    
    def _should_check_update(self, tool, hours=24):
        """Проверять обновления не чаще чем раз в N часов"""
        last = self._cache.get(f"{tool}_check")
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
            return datetime.now() - last_dt > timedelta(hours=hours)
        except:
            return True
    
    def has_ytdlp(self):
        """Проверить наличие yt-dlp"""
        return self.ytdlp_path.exists()
    
    def get_local_version(self):
        """Получить локальную версию yt-dlp"""
        if not self.has_ytdlp():
            return None
        try:
            r = subprocess.run(
                [str(self.ytdlp_path), "--version"],
                capture_output=True, text=True, timeout=10
            )
            return r.stdout.strip() if r.returncode == 0 else None
        except:
            return None
    
    def get_latest_version(self):
        """Получить последнюю версию с GitHub"""
        try:
            r = requests.get(YTDLP_RELEASES_API, timeout=10)
            if r.status_code == 200:
                return r.json().get("tag_name")
        except:
            pass
        return None
    
    def needs_update(self):
        """Нужно ли обновлять yt-dlp"""
        if not self.has_ytdlp():
            return True, None, None
        
        if not self._should_check_update("ytdlp"):
            local = self._cache.get("ytdlp_local")
            latest = self._cache.get("ytdlp_latest")
            if local and latest:
                return local != latest, local, latest
            return False, local, latest
        
        local = self.get_local_version()
        latest = self.get_latest_version()
        
        self._cache["ytdlp_check"] = datetime.now().isoformat()
        self._cache["ytdlp_local"] = local
        self._cache["ytdlp_latest"] = latest
        self._save_cache()
        
        if not local or not latest:
            return False, local, latest
        
        return local != latest, local, latest
    
    def install_or_update(self, progress_callback=None):
        """Установить или обновить yt-dlp"""
        try:
            r = requests.get(YTDLP_RELEASES_API, timeout=10)
            if r.status_code != 200:
                return False, "Не удалось получить список релизов"
            
            data = r.json()
            version = data.get("tag_name", "unknown")
            
            # Выбираем нужный binary
            if SYSTEM == "Windows":
                asset_name = "yt-dlp.exe"
            elif SYSTEM == "Darwin":
                asset_name = "yt-dlp_macos"
            else:
                asset_name = "yt-dlp"
            
            asset_url = None
            for asset in data.get("assets", []):
                if asset["name"] == asset_name:
                    asset_url = asset["browser_download_url"]
                    break
            
            if not asset_url:
                return False, f"Не найден binary для {SYSTEM}"
            
            if progress_callback:
                progress_callback(0.1, f"Скачиваю yt-dlp {version}...")
            
            # Скачиваем
            r = requests.get(asset_url, stream=True, timeout=60)
            total = int(r.headers.get('content-length', 0))
            downloaded = 0
            
            tmp_path = self.ytdlp_path.with_suffix('.tmp')
            with open(tmp_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total > 0:
                            ratio = 0.1 + 0.9 * (downloaded / total)
                            progress_callback(ratio, None)
            
            # Заменяем старый
            if self.ytdlp_path.exists():
                try:
                    self.ytdlp_path.unlink()
                except:
                    pass
            tmp_path.rename(self.ytdlp_path)
            
            # Делаем исполняемым на Unix
            if SYSTEM != "Windows":
                self.ytdlp_path.chmod(
                    self.ytdlp_path.stat().st_mode | 
                    stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
                )
            
            # Обновляем кэш
            self._cache["ytdlp_local"] = version
            self._cache["ytdlp_latest"] = version
            self._cache["ytdlp_check"] = datetime.now().isoformat()
            self._save_cache()
            
            return True, version
        
        except Exception as e:
            return False, str(e)
    
    def ensure_ready(self, progress_callback=None):
        """Убедиться что yt-dlp установлен и актуален"""
        if not self.has_ytdlp():
            self.log("yt-dlp не найден — устанавливаю...", "⬇️")
            return self.install_or_update(progress_callback)
        
        needs, local, latest = self.needs_update()
        if needs:
            self.log(f"Обновляю yt-dlp: {local} → {latest}", "🔄")
            return self.install_or_update(progress_callback)
        
        return True, local


# ═══════════════════════════════════════════════════════
# МЕНЕДЖЕР КОНФИГУРАЦИИ
# ═══════════════════════════════════════════════════════

class ConfigManager:
    LOCAL_CONFIG = APP_DIR / "config.json"
    
    def __init__(self):
        self.config = self._load()
    
    def _default_config(self):
        return {
            "version": APP_VERSION,
            "apis": DEFAULT_APIS,
            "patterns": {
                "url": [r"tiktok\.com", r"vm\.tiktok\.com", r"vt\.tiktok\.com"],
                "hd":  ["hdplay", "hd_play", "hd_video", "video_hd"],
                "sd":  ["play", "video", "download", "play_url"],
                "music": [
                    "music", "music_url", "music_play", "audio", "audio_url",
                    "sound", "sound_url", "mp3", "music_info.play",
                    "music_info.url", "music_info.play_url"
                ],
                "cover": ["cover", "origin_cover", "thumbnail"],
            },
        }
    
    def _load(self):
        if self.LOCAL_CONFIG.exists():
            try:
                return json.loads(self.LOCAL_CONFIG.read_text(encoding="utf-8"))
            except:
                pass
        return self._default_config()
    
    def save(self):
        try:
            self.LOCAL_CONFIG.write_text(
                json.dumps(self.config, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except:
            pass
    
    def refresh_from_remote(self):
        try:
            r = requests.get(REMOTE_CONFIG_URL, timeout=5)
            if r.status_code == 200:
                remote = r.json()
                self.config.update(remote)
                self.save()
                return True, remote.get("version", "?")
        except:
            pass
        return False, "no response"
    
    def get_apis(self):
        apis = self.config.get("apis", DEFAULT_APIS)
        return sorted(apis, key=lambda x: x.get("priority", 99))
    
    def get_patterns(self, key):
        return self.config.get("patterns", {}).get(key, [])


# ═══════════════════════════════════════════════════════
# МЕНЕДЖЕР ОБНОВЛЕНИЙ ПРИЛОЖЕНИЯ
# ═══════════════════════════════════════════════════════

class UpdateManager:
    @staticmethod
    def check_update():
        try:
            r = requests.get(GITHUB_API, timeout=5)
            if r.status_code != 200:
                return False, None, None
            data = r.json()
            latest = data.get("tag_name", "").lstrip("v")
            if not latest:
                return False, None, None
            if UpdateManager._is_newer(latest, APP_VERSION):
                for asset in data.get("assets", []):
                    if asset["name"].endswith(".exe"):
                        return True, latest, asset["browser_download_url"]
            return False, latest, None
        except:
            return False, None, None
    
    @staticmethod
    def _is_newer(remote, local):
        try:
            return [int(x) for x in remote.split(".")] > [int(x) for x in local.split(".")]
        except:
            return False
    
    @staticmethod
    def download_update(url, callback=None):
        try:
            tmp_path = APP_DIR / f"{APP_NAME}_update.tmp"
            r = requests.get(url, stream=True, timeout=60)
            total = int(r.headers.get('content-length', 0))
            downloaded = 0
            
            with open(tmp_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if callback and total > 0:
                            callback(downloaded / total)
            
            return True, tmp_path
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def apply_update(tmp_path):
        if not IS_FROZEN:
            return False, "Не из .exe"
        
        current_exe = Path(sys.executable)
        backup_exe = current_exe.with_suffix('.old')
        update_script = APP_DIR / "_update.bat"
        
        bat_content = f'''@echo off
timeout /t 2 /nobreak >nul
del "{backup_exe}"
move "{current_exe}" "{backup_exe}"
move "{tmp_path}" "{current_exe}"
start "" "{current_exe}"
del "{update_script}"
'''
        update_script.write_text(bat_content, encoding="utf-8")
        
        subprocess.Popen(
            ["cmd", "/c", str(update_script)],
            creationflags=subprocess.DETACHED_PROCESS
        )
        sys.exit(0)


# ═══════════════════════════════════════════════════════
# УМНЫЙ API КЛИЕНТ
# ═══════════════════════════════════════════════════════

class SmartTikTokAPI:
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.tiktok.com/",
    }
    
    def __init__(self, config_manager):
        self.cm = config_manager
    
    def get_info(self, url, log_callback=None):
        apis = self.cm.get_apis()
        
        for api in apis:
            name = api.get("name", "?")
            if log_callback:
                log_callback(f"Пробую API: {name}")
            
            try:
                data, err = self._try_api(api, url)
                if data:
                    if log_callback:
                        log_callback(f"✓ {name} ответил")
                    return self._normalize(data, log_callback), None, name
                elif log_callback:
                    log_callback(f"✗ {name}: {err}")
            except Exception as e:
                if log_callback:
                    log_callback(f"✗ {name}: {str(e)[:50]}")
        
        if log_callback:
            log_callback("Пробую прямой парсинг...")
        
        data, err = self._direct_parse(url)
        if data:
            return data, None, "DirectParse"
        
        return None, "Все методы не сработали", None
    
    def _try_api(self, api, url):
        api_url = api["url"]
        method = api.get("method", "POST")
        
        if method == "POST":
            r = requests.post(api_url, data={"url": url, "hd": 1},
                            headers=self.HEADERS, timeout=15)
        else:
            r = requests.get(api_url, params={"url": url},
                           headers=self.HEADERS, timeout=15)
        
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        
        data = r.json()
        if data.get("code") != 0:
            return None, data.get("msg", "Error")
        
        return data.get("data"), None
    
    def _direct_parse(self, url):
        try:
            r = requests.get(url, headers=self.HEADERS, timeout=10, allow_redirects=True)
            html = r.text
            match = re.search(r'"playAddr":"([^"]+)"', html)
            if match:
                video_url = match.group(1).replace("\\u002F", "/")
                return {
                    "play": video_url, "hdplay": video_url,
                    "title": "TikTok Video",
                    "author": {"unique_id": "unknown"},
                    "id": str(hash(url))[-8:],
                }, None
        except:
            pass
        return None, "Direct parse failed"
    
    def _get_nested(self, data, path):
        try:
            keys = path.split(".")
            val = data
            for k in keys:
                val = val.get(k) if isinstance(val, dict) else None
                if val is None:
                    return None
            return val
        except:
            return None
    
    def _normalize(self, data, log_callback=None):
        result = {
            "id": data.get("id", "unknown"),
            "title": data.get("title", "Video"),
            "author": data.get("author", {}),
            "hdplay": None, "play": None, "music": None, "cover": None,
        }
        
        # HD
        for p in self.cm.get_patterns("hd"):
            val = self._get_nested(data, p)
            if val and isinstance(val, str) and val.startswith("http"):
                result["hdplay"] = val
                break
        
        # SD
        for p in self.cm.get_patterns("sd"):
            val = self._get_nested(data, p)
            if val and isinstance(val, str) and val.startswith("http"):
                result["play"] = val
                break
        
        if not result["hdplay"] and result["play"]:
            result["hdplay"] = result["play"]
        
        # Музыка
        for p in self.cm.get_patterns("music"):
            val = self._get_nested(data, p)
            if val and isinstance(val, str) and val.startswith("http"):
                result["music"] = val
                if log_callback:
                    log_callback(f"🎵 Музыка в поле: {p}")
                break
        
        if not result["music"]:
            music_info = data.get("music_info", {})
            if isinstance(music_info, dict):
                for key in ["play", "play_url", "url", "download"]:
                    val = music_info.get(key)
                    if val and isinstance(val, str) and val.startswith("http"):
                        result["music"] = val
                        break
        
        # Обложка
        for p in self.cm.get_patterns("cover"):
            val = self._get_nested(data, p)
            if val and isinstance(val, str) and val.startswith("http"):
                result["cover"] = val
                break
        
        if log_callback:
            log_callback(f"  HD: {'✓' if result['hdplay'] else '✗'} | "
                        f"SD: {'✓' if result['play'] else '✗'} | "
                        f"MP3: {'✓' if result['music'] else '✗'}")
        
        return result
    
    def download(self, url, save_path, callback=None):
        if not url or not url.startswith("http"):
            return False, f"Невалидный URL"
        
        try:
            r = requests.get(url, stream=True, timeout=30,
                           headers={"User-Agent": self.HEADERS["User-Agent"]})
            
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            
            total = int(r.headers.get('content-length', 0))
            downloaded = 0
            
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if callback and total > 0:
                            callback(downloaded / total, downloaded, total)
            
            if save_path.stat().st_size < 1000:
                save_path.unlink()
                return False, "Файл слишком маленький"
            
            return True, save_path
        except Exception as e:
            return False, str(e)


# ═══════════════════════════════════════════════════════
# ИЗВЛЕЧЕНИЕ MP3 ИЗ ВИДЕО
# ═══════════════════════════════════════════════════════

class AudioExtractor:
    def __init__(self, dep_manager):
        self.dep = dep_manager
    
    def extract_from_video(self, video_url, save_path, log_callback=None):
        """Извлечь MP3 из видео используя yt-dlp"""
        
        if not self.dep.has_ytdlp():
            return False, "yt-dlp не установлен"
        
        ytdlp = str(self.dep.ytdlp_path)
        
        try:
            if log_callback:
                log_callback("Извлекаю MP3 через yt-dlp...")
            
            output_template = str(save_path.with_suffix(".%(ext)s"))
            
            cmd = [
                ytdlp,
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "320K",
                "--no-playlist",
                "--quiet",
                "--no-warnings",
                "-o", output_template,
                video_url
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                encoding='utf-8',
                errors='ignore'
            )
            
            mp3_path = save_path.with_suffix(".mp3")
            
            if mp3_path.exists() and mp3_path.stat().st_size > 1000:
                # Переименовываем если нужно
                if save_path != mp3_path:
                    if save_path.exists():
                        save_path.unlink()
                    mp3_path.rename(save_path)
                return True, save_path
            
            # Если yt-dlp не сработал
            if result.stderr:
                return False, result.stderr[:200]
            return False, "Не удалось извлечь аудио"
        
        except subprocess.TimeoutExpired:
            return False, "Таймаут извлечения"
        except Exception as e:
            return False, str(e)


# ═══════════════════════════════════════════════════════
# ПРИЛОЖЕНИЕ
# ═══════════════════════════════════════════════════════

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"TikTok Downloader v{APP_VERSION}")
        self.geometry("450x500")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_dark"])
        
        self.config_manager = ConfigManager()
        self.api = SmartTikTokAPI(self.config_manager)
        self.dep_manager = DependencyManager(log_callback=self.log)
        self.extractor = AudioExtractor(self.dep_manager)
        
        self.video_data = None
        self.downloading = False
        self.dependencies_ready = False
        
        self._build()
        self.log(f"Версия {APP_VERSION}", "ℹ️")
        self.after(300, self._startup_checks)
    
    def _build(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=25, pady=20)
        
        # Заголовок
        tf = ctk.CTkFrame(main, fg_color="transparent")
        tf.pack(fill="x", pady=(0, 5))
        
        ctk.CTkLabel(tf, text="TikTok Downloader",
                    font=ctk.CTkFont("Segoe UI", 20, "bold"),
                    text_color=COLORS["text"]).pack(side="left")
        
        ctk.CTkLabel(tf, text=f"v{APP_VERSION}",
                    font=ctk.CTkFont("Segoe UI", 10),
                    text_color=COLORS["text_dim"]).pack(side="right")
        
        ctk.CTkLabel(main, text="Без водяных знаков · HD · MP3 · Автообновление",
                    font=ctk.CTkFont("Segoe UI", 10),
                    text_color=COLORS["text_dim"]).pack(anchor="w", pady=(0, 12))
        
        # URL
        self.url = ctk.CTkEntry(main, placeholder_text="Вставьте ссылку TikTok...",
                               font=ctk.CTkFont("Segoe UI", 13),
                               fg_color=COLORS["bg_input"], border_color=COLORS["border"],
                               border_width=2, text_color=COLORS["text"],
                               height=42, corner_radius=10)
        self.url.pack(fill="x", pady=(0, 10))
        self.url.bind("<Return>", lambda e: self.start())
        
        # Качество
        self.quality = ctk.StringVar(value="HD без водяного знака")
        ctk.CTkOptionMenu(main, variable=self.quality,
                         values=["HD без водяного знака", "SD без водяного знака", "MP3 (музыка)"],
                         font=ctk.CTkFont("Segoe UI", 12),
                         fg_color=COLORS["bg_input"], button_color=COLORS["accent"],
                         button_hover_color="#cc0040", dropdown_fg_color=COLORS["bg_card"],
                         text_color=COLORS["text"], corner_radius=8, height=38
        ).pack(fill="x", pady=(0, 10))
        
        # Кнопка
        self.btn = ctk.CTkButton(main, text="⬇️  СКАЧАТЬ",
                                font=ctk.CTkFont("Segoe UI", 15, "bold"),
                                fg_color=COLORS["accent"], hover_color="#cc0040",
                                text_color="white", corner_radius=12, height=48,
                                command=self.start, state="disabled")
        self.btn.pack(fill="x", pady=(0, 12))
        
        # Прогресс
        pf = ctk.CTkFrame(main, fg_color="transparent")
        pf.pack(fill="x", pady=(0, 5))
        
        self.status = ctk.CTkLabel(pf, text="Инициализация...",
                                  font=ctk.CTkFont("Segoe UI", 11),
                                  text_color=COLORS["text_dim"])
        self.status.pack(side="left")
        
        self.percent = ctk.CTkLabel(pf, text="",
                                   font=ctk.CTkFont("Segoe UI", 11, "bold"),
                                   text_color=COLORS["accent2"])
        self.percent.pack(side="right")
        
        self.bar = ctk.CTkProgressBar(main, height=8, fg_color=COLORS["bg_input"],
                                     progress_color=COLORS["accent"])
        self.bar.pack(fill="x", pady=(0, 10))
        self.bar.set(0)
        
        # Путь
        path_f = ctk.CTkFrame(main, fg_color="transparent")
        path_f.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(path_f, text=f"📁 {DOWNLOAD_DIR}",
                    font=ctk.CTkFont("Segoe UI", 10),
                    text_color=COLORS["text_dim"]).pack(side="left")
        
        ctk.CTkButton(path_f, text="Открыть", font=ctk.CTkFont("Segoe UI", 10),
                     fg_color="transparent", hover_color=COLORS["bg_input"],
                     text_color=COLORS["accent2"], width=70, height=24,
                     command=self.open_folder).pack(side="right")
        
        # Лог
        self.log_box = ctk.CTkTextbox(main, font=ctk.CTkFont("Consolas", 10),
                                     fg_color=COLORS["bg_card"], text_color=COLORS["text"],
                                     corner_radius=8, height=120, wrap="word")
        self.log_box.pack(fill="x")
    
    def log(self, msg, icon="✓"):
        self.log_box.insert("end", f"[{icon}] {msg}\n")
        self.log_box.see("end")
    
    def open_folder(self):
        try:
            if SYSTEM == "Windows":
                os.startfile(str(DOWNLOAD_DIR))
            elif SYSTEM == "Darwin":
                subprocess.run(["open", str(DOWNLOAD_DIR)])
            else:
                subprocess.run(["xdg-open", str(DOWNLOAD_DIR)])
        except Exception as e:
            self.log(f"Ошибка: {e}", "✗")
    
    def is_tiktok_url(self, url):
        return any(re.search(p, url) for p in self.config_manager.get_patterns("url"))
    
    # ── СТАРТОВЫЕ ПРОВЕРКИ ──
    
    def _startup_checks(self):
        threading.Thread(target=self._startup_thread, daemon=True).start()
    
    def _startup_thread(self):
        # 1. Проверяем и устанавливаем yt-dlp
        self.after(0, lambda: self.status.configure(text="Проверка yt-dlp..."))
        self.after(0, lambda: self.log("Проверяю yt-dlp...", "🔧"))
        
        def dep_progress(ratio, msg):
            if msg:
                self.after(0, lambda: self.log(msg, "⬇️"))
            self.after(0, lambda: self.bar.set(ratio * 0.5))
            self.after(0, lambda: self.percent.configure(text=f"{int(ratio * 50)}%"))
        
        ok, result = self.dep_manager.ensure_ready(dep_progress)
        
        if ok:
            self.after(0, lambda: self.log(f"✓ yt-dlp v{result} готов", "✓"))
            self.dependencies_ready = True
        else:
            self.after(0, lambda: self.log(f"✗ yt-dlp: {result}", "✗"))
            self.after(0, lambda: self.log("MP3 может не работать", "⚠️"))
        
        # 2. Обновляем конфиг
        self.after(0, lambda: self.status.configure(text="Проверка конфига..."))
        self.after(0, lambda: self.bar.set(0.6))
        
        ok, result = self.config_manager.refresh_from_remote()
        if ok:
            self.after(0, lambda: self.log(f"✓ Конфиг обновлён (v{result})", "📡"))
            self.api = SmartTikTokAPI(self.config_manager)
        else:
            self.after(0, lambda: self.log("Локальный конфиг", "ℹ️"))
        
        # 3. Проверяем обновления приложения
        self.after(0, lambda: self.status.configure(text="Проверка обновлений..."))
        self.after(0, lambda: self.bar.set(0.8))
        
        has_update, latest, url = UpdateManager.check_update()
        if has_update and url:
            self.after(0, lambda: self.log(f"🔄 Доступна v{latest}!", "🔄"))
            self.after(0, lambda: self._show_update_dialog(latest, url))
        elif latest:
            self.after(0, lambda: self.log(f"✓ Версия актуальна: {APP_VERSION}", "✓"))
        else:
            self.after(0, lambda: self.log("Не удалось проверить обновления", "ℹ️"))
        
        # 4. Готово
        self.after(0, lambda: self.bar.set(1.0))
        self.after(0, lambda: self.percent.configure(text=""))
        self.after(0, lambda: self.status.configure(text="Готов к работе"))
        self.after(0, lambda: self.btn.configure(state="normal"))
        
        # Сбрасываем прогресс-бар через секунду
        self.after(1500, lambda: self.bar.set(0))
    
    def _show_update_dialog(self, new_version, download_url):
        from tkinter import messagebox
        if messagebox.askyesno(
            "Доступно обновление",
            f"Новая версия: {new_version}\n"
            f"Текущая версия: {APP_VERSION}\n\n"
            f"Обновить сейчас?"
        ):
            self._download_and_apply_update(download_url)
    
    def _download_and_apply_update(self, url):
        self.log(f"Скачиваю обновление...", "⬇️")
        self.btn.configure(state="disabled")
        
        def on_progress(ratio):
            p = int(ratio * 100)
            self.after(0, lambda: self.bar.set(ratio))
            self.after(0, lambda: self.percent.configure(text=f"{p}%"))
            self.after(0, lambda: self.status.configure(text=f"Обновление: {p}%"))
        
        def worker():
            ok, result = UpdateManager.download_update(url, on_progress)
            if ok:
                self.after(0, lambda: self.log("Обновление скачано, применяю...", "✓"))
                UpdateManager.apply_update(result)
            else:
                self.after(0, lambda: self.log(f"Ошибка: {result}", "✗"))
                self.after(0, lambda: self.btn.configure(state="normal"))
        
        threading.Thread(target=worker, daemon=True).start()
    
    # ── ОСНОВНАЯ ЛОГИКА ──
    
    def start(self):
        url = self.url.get().strip()
        
        if not url:
            self.log("Вставьте ссылку", "✗"); return
        if not self.is_tiktok_url(url):
            self.log("Не TikTok ссылка", "✗"); return
        if self.downloading:
            self.log("Уже скачивается...", "!"); return
        
        # Проверяем что MP3 возможен
        if "MP3" in self.quality.get() and not self.dependencies_ready:
            self.log("yt-dlp не готов — MP3 может не работать", "⚠️")
        
        self.downloading = True
        self.btn.configure(state="disabled", text="⏳ Загрузка...")
        self.bar.set(0)
        self.percent.configure(text="")
        
        threading.Thread(target=self.worker, args=(url,), daemon=True).start()
    
    def worker(self, url):
        try:
            self.after(0, lambda: self.status.configure(text="Поиск видео..."))
            
            def log_api(msg):
                self.after(0, lambda: self.log(msg, "🔍"))
            
            data, err, api_name = self.api.get_info(url, log_api)
            
            if err or not data:
                self.after(0, lambda: self.log(f"Ошибка: {err}", "✗"))
                self.after(0, self.finish); return
            
            self.video_data = data
            self.after(0, lambda: self.log(f"✓ API: {api_name}"))
            self.after(0, lambda: self.log(f"✓ Видео: {data.get('title', '?')[:35]}"))
            
            # Выбор URL
            q = self.quality.get()
            download_url = None
            ext = "mp4"
            need_extract_audio = False
            
            if "HD" in q:
                download_url = data.get("hdplay") or data.get("play")
            elif "SD" in q:
                download_url = data.get("play") or data.get("hdplay")
            elif "MP3" in q:
                download_url = data.get("music")
                ext = "mp3"
                
                if not download_url:
                    video_url = data.get("hdplay") or data.get("play")
                    if video_url and self.dependencies_ready:
                        self.after(0, lambda: self.log("Извлекаю MP3 из видео...", "🎵"))
                        need_extract_audio = True
                        download_url = video_url
                    elif video_url:
                        self.after(0, lambda: self.log("yt-dlp не готов, сохраню MP4", "⚠️"))
                        ext = "mp4"
                        download_url = video_url
                    else:
                        self.after(0, lambda: self.log("Не найдено ни видео, ни музыки", "✗"))
                        self.after(0, self.finish)
                        return
            
            if not download_url:
                self.after(0, lambda: self.log("URL не найден", "✗"))
                self.after(0, self.finish); return
            
            # Имя файла
            author = data.get("author", {})
            if isinstance(author, dict):
                author = author.get("unique_id", "user")
            author = re.sub(r'[^\w\-]', '_', str(author))[:20]
            vid_id = str(data.get("id", "v"))[-8:]
            filename = f"{author}_{vid_id}.{ext}"
            save_path = DOWNLOAD_DIR / filename
            
            # Скачивание
            self.after(0, lambda: self.status.configure(text="Скачиваю..."))
            self.after(0, lambda: self.log(f"Сохраняю: {filename}"))
            
            def progress(ratio, dl, total):
                p = int(ratio * 100)
                dl_mb = dl / (1024 * 1024)
                tot_mb = total / (1024 * 1024)
                self.after(0, lambda: self.bar.set(ratio))
                self.after(0, lambda: self.percent.configure(text=f"{p}%"))
                self.after(0, lambda: self.status.configure(
                    text=f"{dl_mb:.1f} / {tot_mb:.1f} MB"
                ))
            
            ok, result = self.api.download(download_url, save_path, progress)
            
            if ok:
                # Извлечение MP3 из видео если нужно
                if need_extract_audio:
                    self.after(0, lambda: self.log("Конвертация в MP3...", "🎵"))
                    self.after(0, lambda: self.status.configure(text="Конвертация..."))
                    
                    def ext_log(msg):
                        self.after(0, lambda: self.log(msg, "⚡"))
                    
                    ok2, result2 = self.extractor.extract_from_video(
                        download_url, save_path, ext_log
                    )
                    
                    if ok2:
                        # Удаляем временное mp4 если есть
                        tmp_mp4 = save_path.with_suffix(".mp4")
                        if tmp_mp4.exists() and tmp_mp4 != save_path:
                            try:
                                tmp_mp4.unlink()
                            except:
                                pass
                    else:
                        self.after(0, lambda: self.log(f"Конвертация: {result2}", "⚠️"))
                        self.after(0, lambda: self.log("Сохраняю как MP4", "ℹ️"))
                        mp4_path = save_path.with_suffix(".mp4")
                        try:
                            save_path.rename(mp4_path)
                            save_path = mp4_path
                        except:
                            pass
                
                if save_path.exists():
                    size = save_path.stat().st_size / (1024 * 1024)
                    self.after(0, lambda: self.log(f"✓ Готово: {size:.2f} MB", "✓"))
                    self.after(0, lambda: self.status.configure(text="✓ Готово!"))
                    self.after(0, lambda: self.percent.configure(text="100%"))
                    self.after(0, lambda: self.bar.set(1.0))
            else:
                self.after(0, lambda: self.log(f"Ошибка: {result}", "✗"))
                self.after(0, lambda: self.status.configure(text="Ошибка"))
        
        except Exception as e:
            self.after(0, lambda: self.log(f"Исключение: {e}", "✗"))
        
        finally:
            self.after(0, self.finish)
    
    def finish(self):
        self.downloading = False
        self.btn.configure(state="normal", text="⬇️  СКАЧАТЬ")


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = App()
    app.mainloop()