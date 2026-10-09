import asyncio
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from typing import Literal

import yt_dlp
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

APP_DIR = Path(__file__).resolve().parent
MAX_PLAYLIST_ITEMS = max(1, int(os.getenv("MAX_PLAYLIST_ITEMS", "30")))
MAX_CONCURRENT_DOWNLOADS = max(1, int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2")))
CORS_ORIGINS = [
    x.strip() for x in os.getenv(
        "CORS_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080"
    ).split(",") if x.strip()
]
download_slots = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

app = FastAPI(title="FluxTube API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtu.be", "www.youtu.be",
}


def validate_youtube_url(raw: str) -> str:
    raw = raw.strip()
    if len(raw) > 2048:
        raise ValueError("URL is too long.")
    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower().rstrip(".")
    except Exception:
        raise ValueError("Invalid URL.")
    if parsed.scheme not in ("https", "http") or host not in YOUTUBE_HOSTS:
        raise ValueError("Only public YouTube URLs are accepted.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not accepted.")
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        if parsed.path not in ("/watch", "/playlist", "/shorts", "/live", "/embed"):
            raise ValueError("This YouTube URL type is not supported.")
    return raw


class InfoRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def check_url(cls, v):
        return validate_youtube_url(v)


class DownloadRequest(BaseModel):
    url: str
    mode: Literal["video", "audio"] = "video"
    quality: Literal["best", "1080", "720", "480", "360"] = "best"
    playlist_items: list[int] = Field(default_factory=list, max_length=MAX_PLAYLIST_ITEMS)

    @field_validator("url")
    @classmethod
    def check_url(cls, v):
        return validate_youtube_url(v)

    @field_validator("playlist_items")
    @classmethod
    def check_playlist_items(cls, values):
        if any((not isinstance(n, int)) or n < 1 for n in values):
            raise ValueError("Playlist positions must be positive 1-based integers.")
        if len(set(values)) != len(values):
            raise ValueError("Duplicate playlist positions are not accepted.")
        return values


def clean_title(value: str, max_len: int = 100) -> str:
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value or "youtube_download")
    value = re.sub(r"\s+", " ", value).strip(" ._")
    return (value[:max_len] or "youtube_download")


def base_ydl_opts():
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "ignoreerrors": False,
        "socket_timeout": 20,
        "retries": 2,
        "extractor_retries": 2,
        "playlistend": MAX_PLAYLIST_ITEMS,
    }


def get_info(url: str):
    opts = base_ydl_opts()
    opts.update({"skip_download": True, "extract_flat": "in_playlist"})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not read video details: {str(exc)[:240]}")
    if not data:
        raise HTTPException(status_code=422, detail="No video information was returned.")
    entries = data.get("entries")
    is_playlist = entries is not None
    items = []
    if is_playlist:
        for pos, entry in enumerate(entries, start=1):
            if not entry:
                continue
            items.append({
                "position": pos,
                "id": entry.get("id"),
                "title": entry.get("title") or f"Video {pos}",
                "duration": entry.get("duration"),
                "url": entry.get("url") or entry.get("webpage_url"),
            })
    else:
        items = [{
            "position": 1,
            "id": data.get("id"),
            "title": data.get("title") or "YouTube video",
            "duration": data.get("duration"),
            "url": data.get("webpage_url") or url,
        }]
    return {
        "title": data.get("title") or "YouTube media",
        "thumbnail": data.get("thumbnail"),
        "duration": data.get("duration"),
        "uploader": data.get("uploader") or data.get("channel"),
        "is_playlist": is_playlist,
        "playlist_count": data.get("playlist_count") or len(items),
        "items": items[:MAX_PLAYLIST_ITEMS],
        "max_playlist_items": MAX_PLAYLIST_ITEMS,
    }


@app.get("/")
def root():
    return {"name": "FluxTube API", "status": "ok", "health": "/health", "docs": "/docs"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "max_playlist_items": MAX_PLAYLIST_ITEMS,
        "download_slots": MAX_CONCURRENT_DOWNLOADS,
    }


@app.post("/api/info")
def api_info(body: InfoRequest):
    return get_info(body.url)


def remove_tree(path: str):
    shutil.rmtree(path, ignore_errors=True)


@app.post("/api/download")
async def api_download(body: DownloadRequest, background_tasks: BackgroundTasks):
    # A bounded semaphore prevents unlimited simultaneous resource-heavy downloads.
    if download_slots.locked():
        raise HTTPException(status_code=429, detail="Download server is busy. Try again shortly.")
    await download_slots.acquire()
    temp_dir = tempfile.mkdtemp(prefix="fluxtube-")
    try:
        outtmpl = str(Path(temp_dir) / "%(title).100B_%(id)s.%(ext)s")
        opts = base_ydl_opts()
        opts.update({
            "outtmpl": outtmpl,
            "noplaylist": not bool(body.playlist_items) and False,
            "restrictfilenames": True,
            "windowsfilenames": True,
            "overwrites": False,
            "continuedl": False,
            "concurrent_fragment_downloads": 2,
            "format": (
                "bestaudio/best" if body.mode == "audio" else
                (f"bestvideo[height<={body.quality}]+bestaudio/best/"
                 f"best[height<={body.quality}]" if body.quality != "best" else
                 "bestvideo+bestaudio/best")
            ),
        })
        if body.playlist_items:
            opts["playlist_items"] = ",".join(str(x) for x in body.playlist_items)
        if body.mode == "audio":
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        try:
            # yt-dlp is called directly as a library; no shell commands or user-built command strings.
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([body.url])
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Download failed: {str(exc)[:240]}")

        candidates = [
            p for p in Path(temp_dir).iterdir()
            if p.is_file() and not p.name.endswith((".part", ".ytdl"))
        ]
        if not candidates:
            raise HTTPException(status_code=422, detail="No downloadable media file was produced.")
        candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
        if len(candidates) == 1:
            file_path = candidates[0]
            background_tasks.add_task(remove_tree, temp_dir)
            return FileResponse(
                path=str(file_path),
                filename=clean_title(file_path.name),
                media_type="application/octet-stream",
                background=background_tasks,
            )

        # Multiple selected playlist videos are packaged as a ZIP for one browser download.
        import zipfile
        zip_path = Path(temp_dir) / "FluxTube_Playlist.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in candidates:
                if p != zip_path:
                    zf.write(p, arcname=clean_title(p.name))
        background_tasks.add_task(remove_tree, temp_dir)
        return FileResponse(
            path=str(zip_path),
            filename="FluxTube_Playlist.zip",
            media_type="application/zip",
            background=background_tasks,
        )
    except Exception:
        remove_tree(temp_dir)
        raise
    finally:
        download_slots.release()
