#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════╗
║   Professional Media Downloader Bot                  ║
║   YouTube • Instagram • TikTok                       ║
║   Admin Panel • SQLite • Statistika • Playlist       ║
╚══════════════════════════════════════════════════════╝
"""

import asyncio
import contextlib
import logging
import os
import re
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from dotenv import load_dotenv
import yt_dlp
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, FSInputFile, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ═══════════════════════════════════════════════════════
#  SOZLAMALAR
# ═══════════════════════════════════════════════════════
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ✅ TO'G'RILANDI
BOT_TOKEN     : str = os.getenv("BOT_TOKEN", "")
ADMIN_IDS_RAW : str = os.getenv("ADMIN_IDS", "")
CHANNEL_ID    : str = os.getenv("CHANNEL_ID", "")
CHANNEL_LINK  : str = os.getenv("CHANNEL_LINK", "")

ADMIN_IDS: set[int] = {
    int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()
}

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
FFMPEG_PATH    = r"C:\Users\IT PARK\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
TIKTOK_COOKIES = Path("tiktok_cookies.txt")

# ═══════════════════════════════════════════════════════
#  TIKWM API — TikTok yuklab olish
# ═══════════════════════════════════════════════════════
async def tiktok_download(url: str, audio_only: bool = False) -> Optional[Path]:
    """
    Bir nechta API orqali TikTok yuklab oladi.
    audio_only=True bo'lsa MP3, aks holda MP4.
    """
    import aiohttp as _aiohttp
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    # SSL kontekst — TikTok uchun
    import ssl
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    connector = _aiohttp.TCPConnector(ssl=ssl_ctx)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.tiktok.com/",
    }

    async with _aiohttp.ClientSession(connector=connector, headers=headers) as session:

        # ── API 1: tikwm.com ──────────────────────────────
        try:
            async with session.post(
                "https://www.tikwm.com/api/",
                data={"url": url, "hd": 1},
                timeout=_aiohttp.ClientTimeout(total=20)
            ) as resp:
                data = await resp.json(content_type=None)

            if data.get("code") == 0:
                d = data["data"]
                if audio_only:
                    dl_url = d.get("music_info", {}).get("play") or d.get("play")
                    ext = "mp3"
                else:
                    dl_url = d.get("hdplay") or d.get("play")
                    ext = "mp4"

                if dl_url:
                    out = DOWNLOAD_DIR / f"tiktok_{ts}.{ext}"
                    async with session.get(dl_url, timeout=_aiohttp.ClientTimeout(total=60)) as r:
                        if r.status == 200:
                            with open(out, "wb") as f:
                                async for chunk in r.content.iter_chunked(65536):
                                    f.write(chunk)
                    if out.exists() and out.stat().st_size > 5000:
                        log.info("✅ tikwm.com orqali yuklandi")
                        return out
        except Exception as e:
            log.warning("tikwm xatolik: %s", e)

        # ── API 2: lovetik.com ────────────────────────────
        try:
            async with session.post(
                "https://lovetik.com/api/ajax/search",
                data={"query": url},
                timeout=_aiohttp.ClientTimeout(total=20)
            ) as resp:
                data = await resp.json(content_type=None)

            links = data.get("links", [])
            dl_url = None
            for link in links:
                if audio_only and link.get("type") == "mp3":
                    dl_url = link.get("a")
                    break
                elif not audio_only and link.get("type") == "mp4":
                    dl_url = link.get("a")
                    break

            if dl_url:
                ext = "mp3" if audio_only else "mp4"
                out = DOWNLOAD_DIR / f"tiktok_{ts}.{ext}"
                async with session.get(dl_url, timeout=_aiohttp.ClientTimeout(total=60)) as r:
                    if r.status == 200:
                        with open(out, "wb") as f:
                            async for chunk in r.content.iter_chunked(65536):
                                f.write(chunk)
                if out.exists() and out.stat().st_size > 5000:
                    log.info("✅ lovetik.com orqali yuklandi")
                    return out
        except Exception as e:
            log.warning("lovetik xatolik: %s", e)

        # ── API 3: savetik.app ────────────────────────────
        try:
            async with session.post(
                "https://savetik.co/api/ajaxSearch",
                data={"q": url, "lang": "en"},
                timeout=_aiohttp.ClientTimeout(total=20)
            ) as resp:
                data = await resp.json(content_type=None)

            import re as _re
            html = data.get("data", "")
            if audio_only:
                urls = _re.findall(r'href="(https?://[^"]+\.mp3[^"]*)"', html)
            else:
                urls = _re.findall(r'href="(https?://[^"]+\.mp4[^"]*)"', html)

            if urls:
                ext = "mp3" if audio_only else "mp4"
                out = DOWNLOAD_DIR / f"tiktok_{ts}.{ext}"
                async with session.get(urls[0], timeout=_aiohttp.ClientTimeout(total=60)) as r:
                    if r.status == 200:
                        with open(out, "wb") as f:
                            async for chunk in r.content.iter_chunked(65536):
                                f.write(chunk)
                if out.exists() and out.stat().st_size > 5000:
                    log.info("✅ savetik.co orqali yuklandi")
                    return out
        except Exception as e:
            log.warning("savetik xatolik: %s", e)

    log.error("❌ Barcha TikTok API lar ishlamadi")
    return None


async def tikwm_download(url: str) -> Optional[Path]:
    return await tiktok_download(url, audio_only=False)


async def tikwm_audio(url: str) -> Optional[Path]:
    return await tiktok_download(url, audio_only=True)


DB_PATH      = Path("bot.db")
MAX_SIZE     = 50 * 1024 * 1024   # 50 MB

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

PLATFORMS: dict[str, tuple[str, ...]] = {
    "youtube":   ("youtube.com", "youtu.be"),
    "instagram": ("instagram.com", "instagr.am"),
    "tiktok":    ("tiktok.com", "vm.tiktok.com", "vt.tiktok.com"),
}

PLATFORM_EMOJI = {
    "youtube":   "▶️ YouTube",
    "instagram": "📸 Instagram",
    "tiktok":    "🎵 TikTok",
}


# ═══════════════════════════════════════════════════════
#  MA'LUMOTLAR BAZASI
# ═══════════════════════════════════════════════════════
class Database:
    def __init__(self, path: Path):
        self.path = path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init(self):
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT,
                    full_name   TEXT,
                    joined_at   TEXT,
                    is_banned   INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS downloads (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER,
                    platform    TEXT,
                    media_type  TEXT,
                    title       TEXT,
                    created_at  TEXT
                );
            """)
        log.info("✅ Database tayyor: %s", self.path)

    def add_user(self, user_id: int, username: str, full_name: str):
        with self._conn() as c:
            c.execute("""
                INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, username or "", full_name or "", datetime.now().isoformat()))
            c.execute("""
                UPDATE users SET username=?, full_name=?
                WHERE user_id=?
            """, (username or "", full_name or "", user_id))

    def is_banned(self, user_id: int) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,)).fetchone()
            return bool(row and row[0])

    def get_all_users(self) -> list[tuple]:
        with self._conn() as c:
            return c.execute("SELECT user_id, username, full_name, joined_at FROM users WHERE is_banned=0").fetchall()

    def get_user_count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM users WHERE is_banned=0").fetchone()[0]

    def get_today_users(self) -> int:
        today = date.today().isoformat()
        with self._conn() as c:
            return c.execute(
                "SELECT COUNT(*) FROM users WHERE joined_at LIKE ? AND is_banned=0",
                (f"{today}%",)
            ).fetchone()[0]

    def log_download(self, user_id: int, platform: str, media_type: str, title: str):
        with self._conn() as c:
            c.execute("""
                INSERT INTO downloads (user_id, platform, media_type, title, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, platform, media_type, title[:100], datetime.now().isoformat()))

    def get_download_count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]

    def get_today_downloads(self) -> int:
        today = date.today().isoformat()
        with self._conn() as c:
            return c.execute(
                "SELECT COUNT(*) FROM downloads WHERE created_at LIKE ?",
                (f"{today}%",)
            ).fetchone()[0]

    def get_platform_stats(self) -> list[tuple]:
        with self._conn() as c:
            return c.execute("""
                SELECT platform, COUNT(*) as cnt
                FROM downloads GROUP BY platform ORDER BY cnt DESC
            """).fetchall()

    def get_top_users(self, limit: int = 5) -> list[tuple]:
        with self._conn() as c:
            return c.execute("""
                SELECT d.user_id, u.username, u.full_name, COUNT(*) as cnt
                FROM downloads d
                LEFT JOIN users u ON d.user_id = u.user_id
                GROUP BY d.user_id ORDER BY cnt DESC LIMIT ?
            """, (limit,)).fetchall()


db = Database(DB_PATH)


# ═══════════════════════════════════════════════════════
#  KANAL OBUNASI
# ═══════════════════════════════════════════════════════
async def check_subscription(bot: Bot, user_id: int) -> bool:
    if not CHANNEL_ID:
        return True
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status not in (
            ChatMemberStatus.LEFT,
            ChatMemberStatus.KICKED,
            ChatMemberStatus.BANNED,
        )
    except Exception:
        return True


def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=CHANNEL_LINK or "https://t.me")],
        [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")],
    ])


# ═══════════════════════════════════════════════════════
#  MEDIA DOWNLOADER
# ═══════════════════════════════════════════════════════
@dataclass
class FormatInfo:
    height: int
    format_id: str
    filesize: int
    ext: str

    @property
    def label(self) -> str:
        return f"{self.height}p"

    @property
    def size_mb(self) -> float:
        return self.filesize / (1024 * 1024)


@dataclass
class VideoInfo:
    title: str
    duration: int
    url: str
    platform: str
    uploader: str = ""
    is_playlist: bool = False
    playlist_count: int = 0
    formats: list[FormatInfo] = field(default_factory=list)

    @property
    def duration_str(self) -> str:
        if not self.duration:
            return "—"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def detect_platform(url: str) -> Optional[str]:
    u = url.lower()
    for name, domains in PLATFORMS.items():
        if any(d in u for d in domains):
            return name
    return None


def is_playlist_url(url: str) -> bool:
    return "list=" in url and "youtube" in url.lower()


def clean(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)[:80]


def base_ydl_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 60,
        "nocheckcertificate": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
            "Referer": "https://www.tiktok.com/",
        },
    }


def tiktok_ydl_opts() -> dict:
    """TikTok uchun maxsus sozlamalar."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 120,
        "nocheckcertificate": True,
        "retries": 10,
        "fragment_retries": 10,
        "http_chunk_size": 1048576,
        "extractor_args": {"tiktok": {"webpage_download": ["1"]}},
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.tiktok.com/",
        },
    }
    if TIKTOK_COOKIES.exists():
        opts["cookiefile"] = str(TIKTOK_COOKIES)
        log.info("🍪 TikTok cookies ishlatilmoqda")
    # curl_cffi impersonation (agar o'rnatilgan bo'lsa)
    try:
        import curl_cffi
        opts["impersonate"] = "chrome120"
        log.info("✅ curl_cffi impersonation yoqildi")
    except ImportError:
        pass
    return opts


class Downloader:


    async def _fetch_tiktok_info(self, url: str) -> Optional[VideoInfo]:
        """Tikwm API orqali TikTok video ma'lumotlarini oladi."""
        import aiohttp as _aiohttp
        import ssl as _ssl

        # 1. Tikwm API orqali
        try:
            ssl_ctx = _ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = _ssl.CERT_NONE
            conn = _aiohttp.TCPConnector(ssl=ssl_ctx)
            async with _aiohttp.ClientSession(connector=conn) as session:
                async with session.post(
                    "https://www.tikwm.com/api/",
                    data={"url": url, "hd": 1},
                    timeout=_aiohttp.ClientTimeout(total=30)
                ) as resp:
                    data = await resp.json(content_type=None)

            if data.get("code") == 0:
                d = data.get("data", {})
                title = d.get("title") or "TikTok video"
                duration = d.get("duration") or 0
                author = d.get("author", {}).get("nickname") or ""
                return VideoInfo(
                    title=title[:80], duration=duration, url=url,
                    platform="tiktok", uploader=author, formats=[],
                )
        except Exception as e:
            log.warning("Tikwm info xatolik: %s", e)

        # 2. yt-dlp + cookies orqali
        try:
            opts = {**tiktok_ydl_opts(), "extract_flat": True}
            loop = asyncio.get_running_loop()
            def _run():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)
            info = await loop.run_in_executor(None, _run)
            if info:
                return VideoInfo(
                    title=(info.get("title") or "TikTok video")[:80],
                    duration=info.get("duration") or 0,
                    url=url, platform="tiktok",
                    uploader=info.get("uploader") or "",
                    formats=[],
                )
        except Exception as e:
            log.warning("yt-dlp tiktok info xatolik: %s", e)

        return None

    async def fetch_info(self, url: str, platform: str) -> Optional[VideoInfo]:
        # TikTok uchun Tikwm API ishlatamiz
        if platform == "tiktok":
            return await self._fetch_tiktok_info(url)
        
        base = base_ydl_opts()
        opts = {**base, "extract_flat": "in_playlist"}
        try:
            loop = asyncio.get_running_loop()

            def _run():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await loop.run_in_executor(None, _run)
            if not info:
                return None

            is_pl = "entries" in info
            pl_count = len(list(info.get("entries", []))) if is_pl else 0
            if is_pl:
                info = list(info["entries"])[0] if pl_count else info

            title    = (info.get("title") or "Video")[:80]
            uploader = info.get("uploader") or info.get("channel") or ""
            duration = info.get("duration") or 0

            formats: list[FormatInfo] = []
            seen: set[int] = set()
            for f in info.get("formats", []):
                h = f.get("height")
                if not h or h in seen or h > 1080:
                    continue
                if (f.get("vcodec") or "none") == "none":
                    continue
                fs = f.get("filesize") or f.get("filesize_approx") or 0
                if fs <= 0 or fs > MAX_SIZE * 2:
                    continue
                seen.add(h)
                formats.append(FormatInfo(
                    height=h, format_id=f["format_id"],
                    filesize=fs, ext=f.get("ext", "mp4")
                ))
            formats.sort(key=lambda x: x.height)

            return VideoInfo(
                title=title, duration=duration, url=url,
                platform=platform, uploader=uploader,
                is_playlist=is_pl, playlist_count=pl_count,
                formats=formats,
            )
        except Exception as e:
            log.error("fetch_info xatolik: %s", e)
            return None

    async def download_audio(self, url: str) -> Optional[Path]:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        prefix = f"aud_{ts}_"
        opts = {
            **base_ydl_opts(),
            "format": "bestaudio/best",
            "outtmpl": str(DOWNLOAD_DIR / f"{prefix}%(title)s.%(ext)s"),
            "restrictfilenames": True,
            "retries": 3,
            "ffmpeg_location": FFMPEG_PATH,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }
        return await self._download(url, opts, prefix)

    async def download_video(self, url: str, fmt_id: str, platform: str) -> Optional[Path]:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        prefix = f"vid_{ts}_"

        if platform == "tiktok":
            fmt = "best[ext=mp4]/best"
        elif platform == "instagram":
            fmt = f"{fmt_id}/best[ext=mp4]/best"
        else:
            fmt = f"{fmt_id}+bestaudio/best[height<=720][ext=mp4]/best[height<=720]"

        base = tiktok_ydl_opts() if platform == "tiktok" else base_ydl_opts()
        opts = {
            **base,
            "format": fmt,
            "outtmpl": str(DOWNLOAD_DIR / f"{prefix}%(title)s.%(ext)s"),
            "restrictfilenames": True,
            "retries": 5,
            "ffmpeg_location": FFMPEG_PATH,
            "merge_output_format": "mp4",
            "extractor_args": {
                "tiktok": {
                    "webpage_download": True,
                }
            },
        }
        return await self._download(url, opts, prefix)

    async def download_playlist_audio(self, url: str) -> list[Path]:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        prefix = f"pl_{ts}_"
        opts = {
            **base_ydl_opts(),
            "format": "bestaudio/best",
            "outtmpl": str(DOWNLOAD_DIR / f"{prefix}%(playlist_index)s_%(title)s.%(ext)s"),
            "restrictfilenames": True,
            "retries": 2,
            "ffmpeg_location": FFMPEG_PATH,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }
        downloaded: list[Path] = []

        def _on_finish(filepath: str):
            p = Path(filepath)
            if p.exists():
                downloaded.append(p)

        loop = asyncio.get_running_loop()

        def _run():
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.add_post_hook(_on_finish)
                ydl.extract_info(url, download=True)

        try:
            await loop.run_in_executor(None, _run)
        except Exception as e:
            log.error("Playlist xatolik: %s", e)

        if not downloaded:
            downloaded = sorted(DOWNLOAD_DIR.glob(f"{prefix}*"))

        return [p for p in downloaded if p.exists() and p.stat().st_size < MAX_SIZE]

    async def _download(self, url: str, opts: dict, prefix: str) -> Optional[Path]:
        loop = asyncio.get_running_loop()
        downloaded: list[Path] = []

        def _on_finish(fp: str):
            downloaded.append(Path(fp))

        def _run():
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.add_post_hook(_on_finish)
                ydl.extract_info(url, download=True)

        try:
            await loop.run_in_executor(None, _run)
            if downloaded and downloaded[0].exists():
                return downloaded[0]
            for f in sorted(DOWNLOAD_DIR.glob(f"{prefix}*")):
                if f.is_file():
                    return f
        except Exception as e:
            log.error("_download xatolik: %s", e)
        return None


dl = Downloader()


# ═══════════════════════════════════════════════════════
#  FSM HOLATLARI
# ═══════════════════════════════════════════════════════
class States(StatesGroup):
    choosing_type   = State()
    waiting_quality = State()
    downloading     = State()
    admin_broadcast = State()


# ═══════════════════════════════════════════════════════
#  KLAVIATURALAR
# ═══════════════════════════════════════════════════════
def type_kb(has_playlist: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎵 MP3 (Audio)", callback_data="type:audio")
    builder.button(text="🎬 MP4 (Video)", callback_data="type:video")
    if has_playlist:
        builder.button(text="⏬ Butun Playlist (MP3)", callback_data="type:playlist")
    builder.button(text="❌ Bekor", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def quality_kb(formats: list[FormatInfo]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for f in formats[:6]:
        builder.button(
            text=f"🎬 {f.label}  •  {f.size_mb:.1f} MB",
            callback_data=f"dl:{f.format_id}",
        )
    builder.button(text="❌ Bekor", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Statistika",       callback_data="adm:stats"),
            InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="adm:users"),
        ],
        [
            InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="adm:broadcast"),
            InlineKeyboardButton(text="🔄 Yangilash",       callback_data="adm:refresh"),
        ],
    ])


# ═══════════════════════════════════════════════════════
#  BOT VA DISPATCHER
# ═══════════════════════════════════════════════════════
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())


# ═══════════════════════════════════════════════════════
#  YORDAMCHI
# ═══════════════════════════════════════════════════════
async def safe_edit(msg: Message, text: str, **kw):
    with contextlib.suppress(TelegramBadRequest):
        await msg.edit_text(text, **kw)


async def cleanup(*paths: Optional[Path]):
    for p in paths:
        if p and p.exists():
            with contextlib.suppress(OSError):
                p.unlink()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ═══════════════════════════════════════════════════════
#  HANDLERLAR
# ═══════════════════════════════════════════════════════

@dp.message(CommandStart())
async def cmd_start(msg: Message):
    db.add_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    await msg.answer(
        f"👋 Salom, <b>{msg.from_user.full_name}</b>!\n\n"
        "🤖 <b>Professional Media Downloader</b>\n\n"
        "📥 <b>Qo'llab-quvvatlanadigan platformalar:</b>\n"
        "▶️ YouTube — video, musiqa, playlist\n"
        "📸 Instagram — post, reel\n"
        "🎵 TikTok — video va audio\n\n"
        "💡 Havola yuboring va formatni tanlang!\n\n"
        "⚠️ Maksimal fayl hajmi: <b>50 MB</b>"
    )


@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📖 <b>Qo'llanma</b>\n\n"
        "<b>YouTube:</b>\n"
        "• <code>https://youtu.be/xxx</code>\n"
        "• <code>https://youtube.com/playlist?list=xxx</code>\n\n"
        "<b>Instagram:</b>\n"
        "• <code>https://instagram.com/reel/xxx</code>\n\n"
        "<b>TikTok:</b>\n"
        "• <code>https://vm.tiktok.com/xxx</code>\n\n"
        "<b>Buyruqlar:</b>\n"
        "/start — Bosh sahifa\n"
        "/stats — Statistikam\n"
        "/admin — Admin panel\n"
        "/cancel — Bekor qilish"
    )


@dp.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("✅ Amal bekor qilindi.")


@dp.message(Command("stats"))
async def cmd_stats(msg: Message):
    db.add_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    with sqlite3.connect(DB_PATH) as c:
        total = c.execute(
            "SELECT COUNT(*) FROM downloads WHERE user_id=?", (msg.from_user.id,)
        ).fetchone()[0]
        today = c.execute(
            "SELECT COUNT(*) FROM downloads WHERE user_id=? AND created_at LIKE ?",
            (msg.from_user.id, f"{date.today().isoformat()}%")
        ).fetchone()[0]
        by_platform = c.execute(
            "SELECT platform, COUNT(*) FROM downloads WHERE user_id=? GROUP BY platform",
            (msg.from_user.id,)
        ).fetchall()

    lines = "\n".join(f"  {PLATFORM_EMOJI.get(p, p)}: {cnt} ta" for p, cnt in by_platform)
    await msg.answer(
        f"📊 <b>Sizning statistikangiz</b>\n\n"
        f"📥 Jami: <b>{total} ta</b>\n"
        f"📅 Bugun: <b>{today} ta</b>\n\n"
        f"<b>Platformalar:</b>\n{lines or '  Hali yuklamagan'}"
    )


# ── ADMIN ──────────────────────────────────────────────

@dp.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Ruxsat yo'q.")
        return
    await msg.answer(
        f"🔧 <b>Admin Panel</b>\n👤 {msg.from_user.full_name}",
        reply_markup=admin_kb()
    )


@dp.callback_query(F.data.startswith("adm:"))
async def admin_actions(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    action = call.data.removeprefix("adm:")
    await call.answer()

    if action in ("stats", "refresh"):
        pl_lines = "\n".join(
            f"  {PLATFORM_EMOJI.get(p, p)}: <b>{cnt}</b> ta"
            for p, cnt in db.get_platform_stats()
        ) or "  Hali yuklanmagan"

        top_lines = "\n".join(
            f"  {i+1}. @{u or '—'} ({fn}) — <b>{cnt}</b> ta"
            for i, (uid, u, fn, cnt) in enumerate(db.get_top_users(5))
        ) or "  Hali yuklanmagan"

        await safe_edit(call.message,
            "📊 <b>Bot Statistikasi</b>\n\n"
            f"👥 Foydalanuvchilar: <b>{db.get_user_count()}</b>\n"
            f"🆕 Bugun: <b>{db.get_today_users()}</b>\n\n"
            f"📥 Jami yuklashlar: <b>{db.get_download_count()}</b>\n"
            f"📅 Bugun: <b>{db.get_today_downloads()}</b>\n\n"
            f"🌐 <b>Platformalar:</b>\n{pl_lines}\n\n"
            f"🏆 <b>Top 5:</b>\n{top_lines}\n\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}",
            reply_markup=admin_kb()
        )

    elif action == "users":
        users = db.get_all_users()
        lines = [
            f"• <a href='tg://user?id={uid}'>{fn}</a> (@{u or '—'})"
            for uid, u, fn, _ in users[:20]
        ]
        await safe_edit(call.message,
            f"👥 <b>Foydalanuvchilar ({len(users)} ta)</b>\n\n"
            + "\n".join(lines)
            + ("\n\n<i>...va boshqalar</i>" if len(users) > 20 else ""),
            reply_markup=admin_kb()
        )

    elif action == "broadcast":
        await safe_edit(call.message,
            "📢 <b>Xabar yuborish</b>\n\nYubormoqchi bo'lgan xabarni yozing:"
        )
        await state.set_state(States.admin_broadcast)


@dp.message(States.admin_broadcast)
async def do_broadcast(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.clear()
    users = db.get_all_users()
    success = fail = 0
    status = await msg.answer(f"📢 Yuborilmoqda... 0/{len(users)}")

    for i, (uid, *_) in enumerate(users):
        try:
            await bot.send_message(uid, msg.text or msg.caption or "")
            success += 1
        except Exception:
            fail += 1
        if (i + 1) % 20 == 0:
            with contextlib.suppress(TelegramBadRequest):
                await status.edit_text(f"📢 Yuborilmoqda... {i+1}/{len(users)}")
        await asyncio.sleep(0.05)

    await status.edit_text(
        f"✅ <b>Xabar yuborildi!</b>\n\n"
        f"✔️ Muvaffaqiyatli: <b>{success}</b>\n"
        f"❌ Xatolik: <b>{fail}</b>"
    )


# ── KANAL OBUNASI ──────────────────────────────────────

@dp.callback_query(F.data == "check_sub")
async def check_sub_cb(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if await check_subscription(bot, call.from_user.id):
        await safe_edit(call.message, "✅ Rahmat! Endi havolani qayta yuboring.")
        await state.clear()
    else:
        await call.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)


# ── URL QABUL QILISH ───────────────────────────────────

@dp.message(F.text)
async def handle_url(msg: Message, state: FSMContext):
    db.add_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)

    if db.is_banned(msg.from_user.id):
        await msg.answer("🚫 Siz botdan bloklangansiz.")
        return

    url = msg.text.strip()
    if not url.startswith("http"):
        await msg.answer("❓ Havola yuboring yoki /help ni bosing.\n\nYouTube • Instagram • TikTok")
        return

    platform = detect_platform(url)
    if not platform:
        await msg.answer("❌ <b>Noto'g'ri havola</b>\n\nYouTube, Instagram yoki TikTok havolasini yuboring.")
        return

    if not await check_subscription(bot, msg.from_user.id):
        await state.update_data(pending_url=url)
        await msg.answer("📢 <b>Botdan foydalanish uchun kanalga obuna bo'ling!</b>", reply_markup=sub_keyboard())
        return

    status = await msg.answer(f"{PLATFORM_EMOJI[platform]} ma'lumotlari olinmoqda... ⏳")
    info = await dl.fetch_info(url, platform)

    if not info:
        await safe_edit(status,
            "❌ <b>Xatolik</b>\n\n"
            "• Havola noto'g'ri yoki eskirgan\n"
            "• Video/post o'chirilgan\n"
            "• Hisob yopiq (private)"
        )
        return

    is_pl = info.is_playlist and is_playlist_url(url)

    caption = (
        f"{PLATFORM_EMOJI[platform]}\n"
        f"🎬 <b>{info.title}</b>"
        + (f"\n👤 <b>{info.uploader}</b>" if info.uploader else "")
        + (f"\n⏱ <b>{info.duration_str}</b>" if info.duration else "")
        + (f"\n📋 Playlist: <b>{info.playlist_count} ta qo'shiq</b>" if is_pl else "")
        + "\n\n👇 <b>Formatni tanlang:</b>"
    )

    await safe_edit(status, caption, reply_markup=type_kb(has_playlist=is_pl))

    valid_fmts = [f for f in info.formats if f.filesize <= MAX_SIZE]
    await state.update_data(
        url=url, title=info.title, platform=platform,
        is_playlist=is_pl, playlist_count=info.playlist_count,
        formats_data=[
            {"height": f.height, "format_id": f.format_id,
             "filesize": f.filesize, "ext": f.ext}
            for f in valid_fmts
        ],
    )
    await state.set_state(States.choosing_type)


# ── FORMAT TANLASH ─────────────────────────────────────

@dp.callback_query(F.data.startswith("type:"))
async def type_cb(call: CallbackQuery, state: FSMContext):
    await call.answer()
    chosen = call.data.removeprefix("type:")
    data = await state.get_data()
    url, title, platform = data["url"], data["title"], data["platform"]

    if chosen == "audio":
        await safe_edit(call.message, f"🎵 <b>Yuklanmoqda...</b>\n📹 {title}\n\n⏳ Kuting...")
        await state.set_state(States.downloading)
        if platform == "tiktok":
            path = await tikwm_audio(url)
            if not path:
                path = await dl.download_audio(url)
        else:
            path = await dl.download_audio(url)
        await send_audio(call, path, title, platform, state)

    elif chosen == "video":
        fmts = [FormatInfo(**f) for f in data.get("formats_data", [])]
        if not fmts or platform == "tiktok":
            await safe_edit(call.message, f"🎬 <b>Yuklanmoqda...</b>\n📹 {title}\n\n⏳ Kuting...")
            await state.set_state(States.downloading)
            if platform == "tiktok":
                path = await tikwm_download(url)
                if not path:
                    path = await dl.download_video(url, "best", platform)
            else:
                path = await dl.download_video(url, "best", platform)
            await send_video(call, path, title, platform, state)
        else:
            await safe_edit(call.message,
                f"📹 <b>{title}</b>\n\n"
                f"📊 <b>{len(fmts)} ta sifat mavjud</b>\n\n"
                "👇 Kerakli sifatni tanlang:",
                reply_markup=quality_kb(fmts),
            )
            await state.set_state(States.waiting_quality)

    elif chosen == "playlist":
        pl_count = data.get("playlist_count", 0)
        await safe_edit(call.message,
            f"⏬ <b>Playlist yuklanmoqda...</b>\n"
            f"📋 {title}\n🎵 {pl_count} ta qo'shiq\n\n⏳ Kuting..."
        )
        await state.set_state(States.downloading)
        files = await dl.download_playlist_audio(url)

        if not files:
            await safe_edit(call.message, "❌ Playlist yuklanmadi.")
            await state.clear()
            return

        await safe_edit(call.message, f"📤 <b>{len(files)} ta qo'shiq yuborilmoqda...</b>")
        sent = 0
        for fp in files:
            try:
                fname = fp.stem[:60]
                await call.message.answer_audio(
                    audio=FSInputFile(fp, filename=clean(fname) + ".mp3"),
                    title=fname,
                )
                db.log_download(call.from_user.id, platform, "audio", fname)
                sent += 1
            except Exception as e:
                log.error("Playlist yuborishda xatolik: %s", e)
            finally:
                await cleanup(fp)
            await asyncio.sleep(0.3)

        await call.message.answer(f"✅ <b>Playlist yuborildi!</b> {sent}/{len(files)} ta")
        with contextlib.suppress(TelegramBadRequest):
            await call.message.delete()
        await state.clear()


@dp.callback_query(F.data.startswith("dl:"))
async def quality_cb(call: CallbackQuery, state: FSMContext):
    await call.answer()
    fmt_id = call.data.removeprefix("dl:")
    data = await state.get_data()
    url, title, platform = data["url"], data["title"], data["platform"]
    valid = [f["format_id"] for f in data.get("formats_data", [])]

    if fmt_id not in valid:
        await safe_edit(call.message, "❌ Format topilmadi.")
        await state.clear()
        return

    await safe_edit(call.message, f"🎬 <b>Yuklanmoqda...</b>\n📹 {title}\n\n⏳ Kuting...")
    await state.set_state(States.downloading)
    path = await dl.download_video(url, fmt_id, platform)
    await send_video(call, path, title, platform, state)


@dp.callback_query(F.data == "cancel")
async def cancel_cb(call: CallbackQuery, state: FSMContext):
    await call.answer("Bekor qilindi")
    await state.clear()
    await safe_edit(call.message, "✅ Bekor qilindi.")


# ── FAYL YUBORISH ──────────────────────────────────────

async def send_audio(call: CallbackQuery, path: Optional[Path], title: str, platform: str, state: FSMContext):
    if not path or not path.exists():
        await safe_edit(call.message, "❌ Yuklab olishda xatolik.")
        await state.clear()
        return
    try:
        if path.stat().st_size > MAX_SIZE:
            await safe_edit(call.message, "❌ Fayl 50MB dan katta.")
            return
        await safe_edit(call.message, "📤 Yuborilmoqda...")
        await call.message.answer_audio(
            audio=FSInputFile(path, filename=clean(title) + ".mp3"),
            caption=f"🎵 <b>{title}</b>", title=title,
        )
        db.log_download(call.from_user.id, platform, "audio", title)
        with contextlib.suppress(TelegramBadRequest):
            await call.message.delete()
        await call.message.answer("✅ <b>Musiqa yuklandi!</b> Yana havola yuboring.")
    except Exception as e:
        log.error("send_audio: %s", e)
        await call.message.answer(f"❌ Xatolik: <code>{str(e)[:100]}</code>")
    finally:
        await cleanup(path)
        await state.clear()


async def send_video(call: CallbackQuery, path: Optional[Path], title: str, platform: str, state: FSMContext):
    if not path or not path.exists():
        await safe_edit(call.message, "❌ Yuklab olishda xatolik.")
        await state.clear()
        return
    try:
        size = path.stat().st_size
        if size > MAX_SIZE:
            await safe_edit(call.message,
                f"❌ Fayl juda katta: <b>{size/1024/1024:.1f} MB</b>\n"
                "Kichikroq sifatni tanlang."
            )
            return
        await safe_edit(call.message, "📤 Yuborilmoqda...")
        await call.message.answer_video(
            video=FSInputFile(path),
            caption=f"🎬 <b>{title}</b>",
            supports_streaming=True,
        )
        db.log_download(call.from_user.id, platform, "video", title)
        with contextlib.suppress(TelegramBadRequest):
            await call.message.delete()
        await call.message.answer("✅ <b>Video yuklandi!</b> Yana havola yuboring.")
    except Exception as e:
        log.error("send_video: %s", e)
        await call.message.answer(f"❌ Xatolik: <code>{str(e)[:100]}</code>")
    finally:
        await cleanup(path)
        await state.clear()


@dp.message()
async def unknown(msg: Message):
    await msg.answer("❓ Havola yuboring yoki /help ni bosing.")


# ═══════════════════════════════════════════════════════
#  ISHGA TUSHIRISH
# ═══════════════════════════════════════════════════════

async def main():
    if not BOT_TOKEN:
        log.critical("❌ BOT_TOKEN topilmadi! .env faylini tekshiring.")
        return

    log.info("🤖 Bot ishga tushmoqda...")
    log.info("👮 Adminlar: %s", ADMIN_IDS or "sozlanmagan")
    log.info("📢 Kanal: %s", CHANNEL_ID or "yo'q")

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        log.info("Bot to'xtatildi.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ To'xtatildi.")

# cmd  pip install curl_cffi