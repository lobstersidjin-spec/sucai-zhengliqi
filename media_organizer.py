#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
点点素材管理大师
功能：
1. 扫描整理：扫描用户指定文件夹，按拍摄日期/媒体种类/设备分类并移动
2. 超级拷贝：将指定源文件夹拷贝到目标目录，自动整理归类，并哈希校验确保文件完整性
"""

__version__ = "0.7"
PROJECT_NAME = "点点素材管理大师"

import os
import re
import sys
import json
import logging
import shutil
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Set
from dataclasses import dataclass, field

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
except ImportError:
    Image = None
    TAGS = {}

try:
    from hachoir.metadata import extractMetadata
    from hachoir.parser import createParser
except ImportError:
    extractMetadata = None
    createParser = None

LOG_FILE = "media_organizer.log"
_log_fmt = "%(asctime)s - %(levelname)s - %(message)s"
logger = logging.getLogger(__name__)


def get_base_dir() -> Path:
    """程序所在目录（脚本或 exe），用于配置与日志路径；Docker 下可通过环境变量 CONFIG_DIR 指定。"""
    env_dir = os.environ.get("CONFIG_DIR", "").strip()
    if env_dir and os.path.isdir(env_dir):
        return Path(env_dir).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _log_file_path() -> Path:
    return get_base_dir() / LOG_FILE


def get_log_file_path() -> str:
    """日志文件完整路径，供界面显示。"""
    return str(_log_file_path())


logger.setLevel(logging.INFO)
if not logger.handlers:
    _fh = logging.FileHandler(str(_log_file_path()), encoding="utf-8")
    _fh.setFormatter(logging.Formatter(_log_fmt))
    logger.addHandler(_fh)


def reset_log_file():
    """清空日志并写入版本标识。"""
    global logger
    for h in logger.handlers[:]:
        if isinstance(h, logging.FileHandler):
            try:
                h.close()
            except Exception:
                pass
            logger.removeHandler(h)
    with open(_log_file_path(), "w", encoding="utf-8") as f:
        f.write(f"--- 日志已清空 ({PROJECT_NAME} v{__version__}) {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    _fh = logging.FileHandler(str(_log_file_path()), encoding="utf-8")
    _fh.setFormatter(logging.Formatter(_log_fmt))
    logger.addHandler(_fh)


logger.info("%s v%s", PROJECT_NAME, __version__)


# --- 扩展名白名单（与 config 合并后使用）---
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".bmp", ".webp",
                    ".raw", ".cr2", ".nef", ".arw", ".dng"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".webm", ".m4v", ".3gp",
                    ".mpg", ".mpeg", ".mts", ".360", ".insv", ".lrf", ".osv"}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".wma"}
# 全景/360 常用扩展或需单独归类的
PANORAMIC_EXTENSIONS = {".360", ".insv", ".osv"}
LEAVE_IN_PLACE_EXTENSIONS = {".op", ".ed", ".lrprev", ".lock"}
SUPER_COPY_HASH_ALGO = "sha256"
SUPER_COPY_CHUNK_SIZE = 64 * 1024  # 64KB


def _compute_file_hash(path: Path, algo: str = SUPER_COPY_HASH_ALGO) -> Optional[str]:
    """计算文件哈希值，用于超级拷贝的完整性校验。"""
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.new(algo)
    try:
        with open(path, "rb") as f:
            while chunk := f.read(SUPER_COPY_CHUNK_SIZE):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, IOError) as e:
        logger.warning("计算哈希失败 %s: %s", path, e)
        return None


@dataclass
class MediaInfo:
    """单文件媒体信息."""
    path: Path
    media_type: str  # "image" | "video" | "panoramic_video" | "audio"
    shoot_date: Optional[datetime]
    device: str
    date_str: str  # 用于目录名，如 2024-01-15


class Config:
    """配置类。配置与日志路径基于程序所在目录，不依赖 cwd。"""

    def __init__(self, config_file: str = "config.json"):
        self.base_dir = get_base_dir()
        self.config_file = str(self.base_dir / config_file)
        self.load_config()

    def load_config(self):
        default = {
            "source_path": "",
            "output_path": "",
            "super_copy_source": "",
            "super_copy_target": "",
            "image_extensions": list(IMAGE_EXTENSIONS),
            "video_extensions": list(VIDEO_EXTENSIONS),
            "audio_extensions": list(AUDIO_EXTENSIONS),
            "leave_in_place_extensions": list(LEAVE_IN_PLACE_EXTENSIONS),
            "related_same_stem": True,
            "date_fallback": "mtime",
            "device_unknown_name": "未知设备",
            "folder_structure": {
                "date_format": "%Y-%m-%d",
                "video_subfolder": "视频",
                "image_subfolder": "图片",
                "audio_subfolder": "音频",
                "panoramic_subfolder": "全景视频",
                "device_subfolder": True,
            },
            "move_files": True,
            "duplicate_strategy": "rename",
            "delete_empty_folders": False,
            "use_exiftool": True,
            "unified_naming": True,
            "auto_copy": {
                "enabled": False,
                "watch_paths": ["/media"],
                "target_path": "",
                "poll_interval_sec": 60,
            },
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    user = json.load(f)
                self._deep_merge(default, user)
            except Exception as e:
                logger.warning("加载配置失败，使用默认: %s", e)
        for k, v in default.items():
            setattr(self, k, v)
        if not os.path.exists(self.config_file):
            self.save_config()

    def _deep_merge(self, base: dict, override: dict):
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_merge(base[k], v)
            else:
                base[k] = v

    def save_config(self):
        cfg = {
            "source_path": getattr(self, "source_path", ""),
            "output_path": getattr(self, "output_path", ""),
            "super_copy_source": getattr(self, "super_copy_source", ""),
            "super_copy_target": getattr(self, "super_copy_target", ""),
            "image_extensions": getattr(self, "image_extensions", []),
            "video_extensions": getattr(self, "video_extensions", []),
            "audio_extensions": getattr(self, "audio_extensions", []),
            "leave_in_place_extensions": getattr(self, "leave_in_place_extensions", []),
            "related_same_stem": getattr(self, "related_same_stem", True),
            "date_fallback": getattr(self, "date_fallback", "mtime"),
            "device_unknown_name": getattr(self, "device_unknown_name", "未知设备"),
            "folder_structure": getattr(self, "folder_structure", {}),
            "move_files": getattr(self, "move_files", True),
            "duplicate_strategy": getattr(self, "duplicate_strategy", "rename"),
            "delete_empty_folders": getattr(self, "delete_empty_folders", False),
            "use_exiftool": getattr(self, "use_exiftool", True),
            "unified_naming": getattr(self, "unified_naming", True),
            "auto_copy": getattr(self, "auto_copy", {"enabled": False, "watch_paths": ["/media"], "target_path": "", "poll_interval_sec": 60}),
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)


def _sanitize_folder_name(name: str) -> str:
    """替换不宜做目录名的字符."""
    if not name or not name.strip():
        return "未知设备"
    s = re.sub(r'[<>:"/\\|?*]', "_", name.strip())
    return s[:80] if len(s) > 80 else s


def _get_resolution(path: Path, media_type: str, use_exiftool: bool = True) -> Tuple[Optional[int], Optional[int]]:
    """读取宽高（像素）。返回 (width, height)，失败为 (None, None)。"""
    if media_type == "image" and Image:
        try:
            with Image.open(path) as img:
                w, h = img.size
                return (w, h)
        except Exception:
            pass
    if use_exiftool:
        m = _exiftool_get(path, ["ImageWidth", "ImageHeight", "VideoFrameWidth", "VideoFrameHeight"], True)
        for wkey, hkey in [("ImageWidth", "ImageHeight"), ("VideoFrameWidth", "VideoFrameHeight")]:
            w = m.get(wkey, "").strip()
            h = m.get(hkey, "").strip()
            if w.isdigit() and h.isdigit():
                return (int(w), int(h))
    if createParser and extractMetadata and media_type in ("video", "panoramic_video"):
        try:
            parser = createParser(str(path))
            if parser:
                with parser:
                    meta = extractMetadata(parser)
                if meta and "width" in meta and "height" in meta:
                    return (int(meta.get("width", 0)), int(meta.get("height", 0)))
        except Exception:
            pass
    return (None, None)


def _get_frame_rate(path: Path, media_type: str, use_exiftool: bool = True) -> str:
    """读取帧率，返回如 60fps、30fps，非视频或失败返回空字符串。"""
    if media_type not in ("video", "panoramic_video"):
        return ""
    if use_exiftool:
        m = _exiftool_get(path, ["VideoFrameRate", "FrameRate"], True)
        for key in ("VideoFrameRate", "FrameRate"):
            v = m.get(key, "").strip()
            if not v:
                continue
            v = v.replace(",", ".")
            if re.match(r"^\d+(\.\d+)?$", v):
                return f"{int(float(v))}fps"
            match = re.search(r"(\d+(?:\.\d+)?)\s*fps?", v, re.I)
            if match:
                return f"{int(float(match.group(1)))}fps"
    if createParser and extractMetadata:
        try:
            parser = createParser(str(path))
            if parser:
                with parser:
                    meta = extractMetadata(parser)
                if meta and "frame_rate" in meta:
                    r = meta.get("frame_rate")
                    if r is not None:
                        return f"{int(float(r))}fps"
        except Exception:
            pass
    return ""


def _is_date_like_folder(name: str) -> bool:
    """判断文件夹名是否像日期（如 20250816、2025-08-16），这类不当作设备名。"""
    if not name or len(name) > 20:
        return False
    s = name.strip()
    if re.match(r"^\d{8}$", s):
        return True
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return True
    if re.match(r"^\d{4}/\d{2}/\d{2}$", s):
        return True
    return False


def _exiftool_get(path: Path, tags: List[str], use_exiftool: bool) -> Dict[str, str]:
    """用 exiftool 读取指定 tag，返回 {tag: value}。"""
    if not use_exiftool or not path.exists():
        return {}
    try:
        out = subprocess.run(
            ["exiftool", "-s", "-json", "-" + ",".join(tags), str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if out.returncode != 0 or not out.stdout:
            return {}
        data = json.loads(out.stdout)
        if not data or not isinstance(data[0], dict):
            return {}
        return {k: str(v).strip() for k, v in data[0].items() if v is not None and str(v).strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        logger.debug("exiftool 读取失败 %s: %s", path.name, e)
        return {}


def _date_from_exif_pillow(path: Path) -> Optional[datetime]:
    """从图片 EXIF 取拍摄时间（PIL）。"""
    if not Image:
        return None
    try:
        with Image.open(path) as img:
            exif = img.getexif() or {}
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
                    if not value:
                        continue
                    s = value if isinstance(value, str) else str(value)
                    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                        try:
                            return datetime.strptime(s.replace("-", ":").replace(" ", " ")[:19], fmt)
                        except ValueError:
                            continue
    except Exception as e:
        logger.debug("PIL EXIF 日期解析失败 %s: %s", path.name, e)
    return None


def _date_from_hachoir(path: Path) -> Optional[datetime]:
    """从视频/音频用 hachoir 取创建/录制时间."""
    if not createParser or not extractMetadata:
        return None
    try:
        parser = createParser(str(path))
        if not parser:
            return None
        with parser:
            meta = extractMetadata(parser)
        if not meta:
            return None
        for key in ("creation_date", "creation-date", "creation date", "Creation date"):
            if key in meta:
                dt = meta.get(key)
                if hasattr(dt, "year"):
                    return dt
                if isinstance(dt, str):
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M:%S", "%Y-%m-%d"):
                        try:
                            return datetime.strptime(dt[:19].replace(":", "-", 2), fmt)
                        except ValueError:
                            continue
    except Exception as e:
        logger.debug("hachoir 日期解析失败 %s: %s", path.name, e)
    return None


def _device_from_exif_pillow(path: Path) -> str:
    """从图片 EXIF 取设备（Make + Model）。"""
    if not Image:
        return ""
    try:
        with Image.open(path) as img:
            exif = img.getexif() or {}
            make = model = ""
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag == "Make" and value:
                    make = (value if isinstance(value, str) else str(value)).strip()
                elif tag == "Model" and value:
                    model = (value if isinstance(value, str) else str(value)).strip()
            if make or model:
                return f"{make} {model}".strip()
    except Exception as e:
        logger.debug("PIL EXIF 设备解析失败 %s: %s", path.name, e)
    return ""


def _is_panoramic_by_path(path: Path, video_ext: Set[str], panoramic_ext: Set[str]) -> bool:
    ext = path.suffix.lower()
    if ext in panoramic_ext:
        return True
    if ext not in video_ext:
        return False
    name = path.stem.lower()
    if "360" in name or "panoram" in name or "theta" in name or "insta360" in name:
        return True
    return False


def _is_panoramic_by_metadata(path: Path, use_exiftool: bool) -> bool:
    """通过 exiftool 或 XMP 判断是否全景/360."""
    m = _exiftool_get(path, ["ProjectionType", "StitchingSoftware", "Make", "Model"], use_exiftool)
    if m.get("ProjectionType", "").lower() in ("equirectangular", "equirectangular "):
        return True
    if "360" in m.get("Make", "") or "360" in m.get("Model", ""):
        return True
    if "theta" in m.get("Make", "").lower() or "insta360" in (m.get("Make", "") or "").lower():
        return True
    return False


class MediaOrganizer:
    """核心整理逻辑：识别、目标路径、关联文件、移动."""

    def __init__(self, config: Config):
        self.config = config
        self.image_ext = set(x.lower() for x in getattr(config, "image_extensions", []))
        self.video_ext = set(x.lower() for x in getattr(config, "video_extensions", []))
        self.video_ext |= set(x.lower() for x in VIDEO_EXTENSIONS)
        self.audio_ext = set(x.lower() for x in getattr(config, "audio_extensions", []))
        self.leave_ext = set(x.lower() for x in getattr(config, "leave_in_place_extensions", []))
        self.processed_path = Path(config.config_file).parent / "processed_files.json"
        self.processed: Set[str] = set()
        self._load_processed()

    def _load_processed(self):
        if self.processed_path.exists():
            try:
                with open(self.processed_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.processed = set(data.get("paths", []))
            except Exception as e:
                logger.warning("加载已处理记录失败: %s", e)

    def save_processed(self, force: bool = False):
        if not force and not self.processed:
            return
        try:
            with open(self.processed_path, "w", encoding="utf-8") as f:
                json.dump({"paths": list(self.processed)}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("保存已处理记录失败: %s", e)

    def should_leave_in_place(self, filepath: Path) -> bool:
        ext = filepath.suffix.lower()
        if ext in self.leave_ext:
            return True
        if "." in filepath.name and filepath.name.lower().endswith((".fg.op", ".fg.ed")):
            return True
        return False

    def get_media_type(self, path: Path) -> Optional[str]:
        ext = path.suffix.lower()
        if ext in self.image_ext:
            return "image"
        if ext in self.audio_ext:
            return "audio"
        if ext not in self.video_ext:
            return None
        if _is_panoramic_by_path(path, self.video_ext, PANORAMIC_EXTENSIONS):
            return "panoramic_video"
        if getattr(self.config, "use_exiftool", True) and _is_panoramic_by_metadata(path, True):
            return "panoramic_video"
        return "video"

    def get_shoot_date(self, path: Path, media_type: str) -> Optional[datetime]:
        if media_type == "image":
            dt = _date_from_exif_pillow(path)
            if not dt and getattr(self.config, "use_exiftool", True):
                m = _exiftool_get(path, ["DateTimeOriginal", "CreateDate"], True)
                for key in ("DateTimeOriginal", "CreateDate"):
                    if key in m and m[key]:
                        s = m[key].replace("-", ":").replace(" ", " ")[:19]
                        try:
                            dt = datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
                            break
                        except ValueError:
                            pass
            if dt:
                return dt
        else:
            if getattr(self.config, "use_exiftool", True):
                m = _exiftool_get(path, ["CreateDate", "DateTimeOriginal", "MediaCreateDate"], True)
                for key in ("CreateDate", "DateTimeOriginal", "MediaCreateDate"):
                    if key in m and m[key]:
                        s = m[key].replace("-", ":").replace(" ", " ")[:19]
                        try:
                            return datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
                        except ValueError:
                            pass
            dt = _date_from_hachoir(path)
            if dt:
                return dt
        fallback = getattr(self.config, "date_fallback", "mtime")
        if fallback == "mtime":
            try:
                mtime = path.stat().st_mtime
                return datetime.fromtimestamp(mtime)
            except OSError:
                pass
        return None

    def _load_device_suffixes_db(self) -> Dict:
        """加载设备后缀名/命名模式库。"""
        db_path = get_base_dir() / "device_suffixes.json"
        if not db_path.exists():
            return {}
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("加载设备后缀名库失败: %s", e)
            return {}

    def _device_from_filename_pattern(self, path: Path) -> Optional[str]:
        """通过文件名前缀或包含匹配设备库识别设备。文件名中带 DJI 的均视为大疆拍摄。"""
        db = self._load_device_suffixes_db()
        patterns = db.get("device_patterns", {})
        if not patterns:
            return None
        filename = path.stem.upper()
        ext = path.suffix.lower()
        for device_name, pattern in patterns.items():
            extensions = pattern.get("extensions", [])
            ext_ok = not extensions or ext in extensions
            # 前缀匹配
            for prefix in pattern.get("filename_prefixes", []):
                if filename.startswith(prefix.upper()) and ext_ok:
                    return device_name
            # 包含匹配（如文件名中带 DJI 的均视为大疆）
            for sub in pattern.get("filename_contains", []):
                if sub.upper() in filename and ext_ok:
                    return device_name
        return None

    def get_device(self, path: Path, media_type: str) -> str:
        unknown = getattr(self.config, "device_unknown_name", "未知设备")
        if media_type not in ("image", "video", "panoramic_video"):
            return unknown
        # 文件名含 DJI、大疆 或扩展名为 .LRF 的均为大疆拍摄，优先识别
        stem = path.stem
        stem_upper = stem.upper()
        ext_lower = path.suffix.lower()
        if "DJI" in stem_upper or "大疆" in stem:
            return "大疆"
        if media_type in ("video", "panoramic_video") and ext_lower == ".lrf":
            return "大疆"
        if media_type == "image":
            dev = _device_from_exif_pillow(path)
            if not dev and getattr(self.config, "use_exiftool", True):
                m = _exiftool_get(path, ["Make", "Model"], True)
                make = m.get("Make", "").strip()
                model = m.get("Model", "").strip()
                dev = f"{make} {model}".strip()
            if dev:
                return _sanitize_folder_name(dev)
            dev = self._device_from_filename_pattern(path)
            return _sanitize_folder_name(dev) if dev else unknown
        if getattr(self.config, "use_exiftool", True):
            m = _exiftool_get(path, ["Make", "Model"], True)
            make = m.get("Make", "").strip()
            model = m.get("Model", "").strip()
            dev = f"{make} {model}".strip()
            if dev:
                return _sanitize_folder_name(dev)
        dev = self._device_from_filename_pattern(path)
        return _sanitize_folder_name(dev) if dev else unknown

    def find_related_files(self, primary: Path, media_type: str) -> List[Path]:
        """与主文件同目录、同词干（或高度关联）的文件一并移动."""
        if not getattr(self.config, "related_same_stem", True):
            return []
        stem = primary.stem
        parent = primary.parent
        related = []
        for f in parent.iterdir():
            if not f.is_file() or f == primary:
                continue
            if self.should_leave_in_place(f):
                continue
            if f.stem == stem:
                related.append(f)
            elif stem.startswith(f.stem + "_") or f.stem.startswith(stem + "_"):
                related.append(f)
            elif stem.startswith(f.stem + " ") or f.stem.startswith(stem + " "):
                related.append(f)
        return related

    def build_target_dir(self, info: MediaInfo, output_root: Path) -> Path:
        fs = getattr(self.config, "folder_structure", {})
        date_fmt = fs.get("date_format", "%Y-%m-%d")
        date_str = info.date_str
        use_device = fs.get("device_subfolder", True)

        if info.media_type == "image":
            sub = fs.get("image_subfolder", "图片")
        elif info.media_type == "panoramic_video":
            sub = fs.get("panoramic_subfolder", "全景视频")
        elif info.media_type == "video":
            sub = fs.get("video_subfolder", "视频")
        else:
            sub = fs.get("audio_subfolder", "音频")

        p = output_root / date_str / sub
        if use_device and info.media_type in ("image", "video", "panoramic_video"):
            p = p / _sanitize_folder_name(info.device)
        return p

    def _build_unified_basename(self, device: str, date_str: str, resolution_str: str, fps_str: str) -> str:
        """统一命名格式：设备名_拍摄日期[_分辨率][_帧率]，分辨率/帧率未知则不填。"""
        safe = re.sub(r'[<>:"/\\|?*\s]+', "_", str(device).strip()) or "未知设备"
        date_safe = re.sub(r'[<>:"/\\|?*\s]+', "_", str(date_str).strip()) or "无日期"
        parts = [safe, date_safe]
        res_trim = str(resolution_str).strip() if resolution_str else ""
        if res_trim and res_trim != "未知":
            parts.append(re.sub(r'[<>:"/\\|?*\s]+', "_", res_trim))
        fps_trim = str(fps_str).strip() if fps_str else ""
        if fps_trim:
            parts.append(re.sub(r'[<>:"/\\|?*\s]+', "_", fps_trim))
        return "_".join(parts).strip("_")[:120]

    def resolve_destination(
        self, target_dir: Path, filepath: Path, unified_basename: Optional[str] = None
    ) -> Optional[Path]:
        """考虑重复策略得到最终目标路径。unified_basename 若提供则用于统一命名（不含扩展名）。
        目标已存在时：skip/rename 均分配 _2、_3 等新路径，避免文件遗落在子文件夹；仅当目标与源为同一文件时返回原路径。"""
        if unified_basename is not None:
            stem, ext = unified_basename, filepath.suffix
        else:
            stem, ext = filepath.stem, filepath.suffix
        dest = target_dir / f"{stem}{ext}"
        if not dest.exists():
            return dest
        if dest.resolve() == filepath.resolve():
            return dest
        strategy = getattr(self.config, "duplicate_strategy", "rename")
        if strategy == "overwrite":
            return dest
        # skip 与 rename：目标已存在时均分配新名称，确保文件被归类而不遗落
        for i in range(1, 9999):
            dest = target_dir / f"{stem}_{i}{ext}"
            if not dest.exists():
                return dest
        return dest

    def process_file(
        self,
        filepath: Path,
        output_root: Path,
        dry_run: bool = False,
        report_list: Optional[List[Tuple[str, str, Optional[str]]]] = None,
    ) -> bool:
        """处理单个主文件：识别、建目录、移动主文件及关联文件。report_list 用于收集 (动作, 源, 目标或原因)。"""
        path_key = str(filepath.resolve())
        output_resolved = Path(output_root).resolve()
        unknown_dev = _sanitize_folder_name(getattr(self.config, "device_unknown_name", "未知设备"))
        if path_key in self.processed:
            try:
                rel = filepath.resolve().relative_to(output_resolved)
                # 已在「日期/类型/设备」结构下且设备不为「未知设备」则视为已整理，跳过
                if rel.parts and len(rel.parts) >= 3 and re.match(r"^\d{4}-\d{2}-\d{2}$", rel.parts[0]):
                    device_subfolder = rel.parts[2]  # 日期/类型/设备 中的设备
                    if device_subfolder != unknown_dev:
                        logger.info("已整理过(跳过): %s", filepath.name)
                        if report_list is not None:
                            report_list.append(("already_processed", str(filepath), "此前已整理"))
                        return True
            except ValueError:
                pass
            # 在 processed 但不在正确设备下（如 未知设备、其他文件、子文件夹），重新归类
            logger.info("重新归类(曾已记录): %s", filepath.name)

        media_type = self.get_media_type(filepath)
        if not media_type:
            return False

        shoot_date = self.get_shoot_date(filepath, media_type)
        date_str = shoot_date.strftime(
            getattr(self.config, "folder_structure", {}).get("date_format", "%Y-%m-%d")
        ) if shoot_date else "无日期"
        device = self.get_device(filepath, media_type)

        info = MediaInfo(
            path=filepath,
            media_type=media_type,
            shoot_date=shoot_date,
            device=device,
            date_str=date_str,
        )

        target_dir = self.build_target_dir(info, output_root)
        move_files = getattr(self.config, "move_files", True)

        unified_basename = None
        if getattr(self.config, "unified_naming", True):
            w, h = _get_resolution(filepath, media_type, getattr(self.config, "use_exiftool", True))
            res_str = f"{w}x{h}" if (w and h) else ""
            fps_str = _get_frame_rate(filepath, media_type, getattr(self.config, "use_exiftool", True))
            unified_basename = self._build_unified_basename(device, date_str, res_str, fps_str)

        primary_dest = self.resolve_destination(target_dir, filepath, unified_basename)
        if primary_dest is None:
            logger.info("跳过已存在(策略=skip): %s", filepath.name)
            if report_list is not None:
                report_list.append(("skip", str(filepath), "已存在"))
            self.processed.add(path_key)
            return True

        related = self.find_related_files(filepath, media_type)

        if not dry_run and move_files:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(filepath), str(primary_dest))
                logger.info("已移动: %s -> %s", filepath.name, primary_dest)
                if report_list is not None:
                    report_list.append(("move", str(filepath), str(primary_dest)))
            except Exception as e:
                logger.error("移动失败 %s: %s", filepath, e)
                if report_list is not None:
                    report_list.append(("fail", str(filepath), str(e)))
                return False
        else:
            logger.info("[%s] 将移动: %s -> %s", "试运行" if dry_run else "复制模式", filepath.name, primary_dest)
            if report_list is not None:
                report_list.append(("move", str(filepath), str(primary_dest)))
        for r in related:
            r_key = str(r.resolve())
            if r_key in self.processed:
                continue
            r_dest = (
                self.resolve_destination(target_dir, r, unified_basename)
                if unified_basename is not None
                else self.resolve_destination(target_dir, r)
            )
            if r_dest is None:
                self.processed.add(r_key)
                continue
            if not dry_run and move_files:
                try:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(r), str(r_dest))
                    logger.info("已移动关联: %s -> %s", r.name, r_dest.name)
                    if report_list is not None:
                        report_list.append(("related", str(r), str(r_dest)))
                except Exception as e:
                    logger.warning("移动关联失败 %s: %s", r.name, e)
                    if report_list is not None:
                        report_list.append(("fail_related", str(r), str(e)))
            else:
                logger.info("[%s] 将移动关联: %s -> %s", "试运行" if dry_run else "复制", r.name, r_dest)
                if report_list is not None:
                    report_list.append(("related", str(r), str(r_dest)))
            self.processed.add(r_key)

        self.processed.add(path_key)
        return True

    def _remove_empty_dirs(self, root: Path) -> int:
        """递归删除 root 下的空文件夹（自底向上），返回删除数量。"""
        root = root.resolve()
        if not root.exists() or not root.is_dir():
            return 0
        removed = 0
        try:
            for dirpath, dirnames, filenames in os.walk(str(root), topdown=False):
                d = Path(dirpath)
                if d.resolve() == root:
                    continue
                if d.is_dir() and not any(d.iterdir()):
                    try:
                        d.rmdir()
                        removed += 1
                        logger.debug("已删除空文件夹: %s", d)
                    except OSError:
                        pass
        except (OSError, PermissionError) as e:
            logger.warning("清理空文件夹时出错: %s", e)
        return removed

    def _normalize_source_path(self, path: Path) -> Path:
        """规范化源路径：Windows 下 F: 或 F:/ 转为 F:\\ 以明确扫描该盘根目录。"""
        s = str(path).strip().replace("/", os.sep).rstrip(os.sep)
        if os.name == "nt" and len(s) == 2 and s[1] == ":":
            s = s + os.sep
        return Path(s).resolve()

    def _collect_media_files_recursive(self, root: Path) -> List[Path]:
        """递归遍历根目录及所有子目录，收集媒体文件。使用 os.walk(str(root)) 保证 Windows 兼容。"""
        root = self._normalize_source_path(root)
        if not root.is_dir():
            logger.warning("扫描路径不是目录或不存在: %s", root)
            return []
        collected: List[Path] = []
        try:
            root_str = str(root)
            for dirpath, _dirnames, filenames in os.walk(root_str, topdown=True, followlinks=False):
                for name in filenames:
                    p = Path(dirpath) / name
                    if not p.is_file():
                        continue
                    if self.should_leave_in_place(p):
                        continue
                    if self.get_media_type(p) is not None:
                        collected.append(p)
        except (OSError, PermissionError) as e:
            logger.warning("遍历子目录时出错 %s: %s", root, e)
        return collected

    def scan_and_organize(
        self,
        source: Optional[Path] = None,
        output: Optional[Path] = None,
        dry_run: bool = False,
        scan_only: bool = False,
    ) -> Dict:
        """
        扫描源目录并整理到输出目录（含所有子目录）。
        scan_only=True 时仅扫描并返回将执行的操作报告，不移动文件。
        返回 {"mode": "scan_only"|"organize", "source": str, "output": str, "total_media": int,
              "to_process": int, "entries": [(action, src, dest_or_reason), ...]}
        """
        src = source or Path(getattr(self.config, "source_path", "") or ".")
        out = output or Path(getattr(self.config, "output_path", "") or src)
        empty_report = {
            "mode": "scan_only" if scan_only else "organize",
            "source": str(src),
            "output": str(out),
            "total_media": 0,
            "to_process": 0,
            "entries": [],
        }
        if not src.exists() or not src.is_dir():
            logger.error("源路径不存在或不是目录: %s", src)
            return empty_report
        if src.resolve() == out.resolve():
            out = src  # 原地整理到子目录

        collected: List[Path] = self._collect_media_files_recursive(src)
        logger.info("扫描整理: 源目录及子目录共发现 %d 个媒体文件", len(collected))

        seen_stem_dir: Set[Tuple[Path, str]] = set()
        to_process: List[Path] = []
        for p in sorted(collected, key=lambda x: (x.parent, x.name)):
            stem_dir = (p.parent, p.stem)
            if stem_dir in seen_stem_dir:
                continue
            seen_stem_dir.add(stem_dir)
            to_process.append(p)

        report_entries: List[Tuple[str, str, Optional[str]]] = []

        if scan_only:
            for fp in to_process:
                mt = self.get_media_type(fp)
                if not mt:
                    continue
                shoot_date = self.get_shoot_date(fp, mt)
                date_str = (
                    shoot_date.strftime(
                        getattr(self.config, "folder_structure", {}).get("date_format", "%Y-%m-%d")
                    )
                    if shoot_date
                    else "无日期"
                )
                device = self.get_device(fp, mt)
                info = MediaInfo(path=fp, media_type=mt, shoot_date=shoot_date, device=device, date_str=date_str)
                target_dir = self.build_target_dir(info, out)
                unified_basename = None
                if getattr(self.config, "unified_naming", True):
                    w, h = _get_resolution(fp, mt, getattr(self.config, "use_exiftool", True))
                    res_str = f"{w}x{h}" if (w and h) else ""
                    fps_str = _get_frame_rate(fp, mt, getattr(self.config, "use_exiftool", True))
                    unified_basename = self._build_unified_basename(device, date_str, res_str, fps_str)
                primary_dest = self.resolve_destination(target_dir, fp, unified_basename)
                if primary_dest is None:
                    report_entries.append(("skip", str(fp), "已存在"))
                    continue
                report_entries.append(("move", str(fp), str(primary_dest)))
                for r in self.find_related_files(fp, mt):
                    r_dest = (
                        self.resolve_destination(target_dir, r, unified_basename)
                        if unified_basename is not None
                        else self.resolve_destination(target_dir, r)
                    )
                    if r_dest is not None:
                        report_entries.append(("related", str(r), str(r_dest)))
            return {
                "mode": "scan_only",
                "source": str(src),
                "output": str(out),
                "total_media": len(collected),
                "to_process": len(to_process),
                "entries": report_entries,
            }

        for fp in to_process:
            self.process_file(fp, out, dry_run=dry_run, report_list=report_entries)
        self.save_processed(force=True)
        if (
            not dry_run
            and getattr(self.config, "delete_empty_folders", False)
        ):
            n = self._remove_empty_dirs(out)
            if n > 0:
                logger.info("扫描整理: 已清理 %d 个空文件夹", n)
        logger.info("扫描整理完成，共处理 %s 个主文件", len(to_process))
        return {
            "mode": "organize",
            "source": str(src),
            "output": str(out),
            "total_media": len(collected),
            "to_process": len(to_process),
            "entries": report_entries,
        }

    def _copy_file_with_hash_verify(
        self, src: Path, dest: Path, dry_run: bool = False, progress_cb=None
    ) -> Tuple[bool, Optional[str]]:
        """
        拷贝文件并做哈希校验。progress_cb(phase, message, current, total) 用于界面进度与日志。
        phase: "hash_src"|"copy"|"hash_dest"|"verify_ok"|"verify_fail"|"progress"
        """
        def _cb(phase: str, msg: str, cur: Optional[int] = None, total: Optional[int] = None):
            if progress_cb:
                try:
                    progress_cb(phase, msg, cur, total)
                except Exception:
                    pass

        if dry_run:
            logger.info("[超级拷贝 试运行] 将拷贝: %s -> %s", src.name, dest)
            return True, None
        _cb("hash_src", f"计算源文件哈希: {src.name}")
        src_hash = _compute_file_hash(src)
        if src_hash is None:
            _cb("verify_fail", f"失败: 无法计算源文件哈希 - {src.name}")
            return False, "无法计算源文件哈希"
        _cb("copy", f"拷贝中: {src.name}")
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
        except Exception as e:
            _cb("verify_fail", f"失败: 拷贝异常 - {src.name}")
            return False, str(e)
        _cb("hash_dest", f"校验目标哈希: {dest.name}")
        dest_hash = _compute_file_hash(dest)
        if dest_hash is None:
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass
            _cb("verify_fail", f"失败: 无法计算目标哈希 - {dest.name}")
            return False, "无法计算目标文件哈希"
        if src_hash != dest_hash:
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass
            _cb("verify_fail", f"失败: 哈希不一致 - {src.name}")
            return False, f"哈希校验失败: 源={src_hash[:16]}... 目标={dest_hash[:16]}..."
        logger.info("超级拷贝 已校验: %s -> %s", src.name, dest)
        _cb("verify_ok", f"校验通过: {src.name}")
        return True, None

    def super_copy_and_organize(
        self,
        source: Path,
        target: Path,
        dry_run: bool = False,
        progress_cb=None,
    ) -> Dict[str, int]:
        """
        超级拷贝：将源文件夹拷贝到目标目录，按日期/类型/设备自动整理，并做哈希校验。
        返回 {"ok": 成功数, "fail": 失败数, "skip": 跳过数, "report": {...}}。
        """
        stats = {"ok": 0, "fail": 0, "skip": 0, "report": None}
        report = {
            "media_ok": [],      # [(src, dest), ...]
            "media_skip": [],    # [(src, reason), ...]
            "media_fail": [],    # [(src, err), ...]
            "other_ok": [],      # [rel_path, ...]
            "other_fail": [],    # [(rel, err), ...]
        }
        if not source.exists() or not source.is_dir():
            logger.error("超级拷贝: 源路径不存在或不是目录: %s", source)
            return stats
        target.mkdir(parents=True, exist_ok=True)

        source_resolved = self._normalize_source_path(source)
        logger.info("超级拷贝: 扫描源目录（含子目录） %s", source_resolved)
        try:
            collected: List[Path] = self._collect_media_files_recursive(source)
        except (OSError, PermissionError) as e:
            logger.error("超级拷贝: 扫描源目录失败 %s: %s", source, e)
            return stats

        seen_stem_dir: Set[Tuple[Path, str]] = set()
        to_process: List[Path] = []
        for p in sorted(collected, key=lambda x: (x.parent, x.name)):
            stem_dir = (p.parent, p.stem)
            if stem_dir in seen_stem_dir:
                continue
            seen_stem_dir.add(stem_dir)
            to_process.append(p)

        logger.info("超级拷贝: 源目录及子目录共发现 %d 个媒体文件，待处理 %d 个", len(collected), len(to_process))
        if not to_process:
            logger.warning(
                "超级拷贝: 未发现可处理的媒体文件。请确认：1) 源路径下是否有图片/视频/音频；"
                "2) 扩展名是否在 config.json 的 image_extensions / video_extensions / audio_extensions 中。"
            )
            return stats

        total_ops = 0
        for fp in to_process:
            mt = self.get_media_type(fp)
            if mt:
                total_ops += 1 + len(self.find_related_files(fp, mt))
        if progress_cb:
            try:
                progress_cb("progress", "", 0, max(1, total_ops))
            except Exception:
                pass

        copied_paths: Set[Path] = set()
        current_op: int = 0
        for fp in to_process:
            media_type = self.get_media_type(fp)
            if not media_type:
                stats["skip"] += 1
                continue
            shoot_date = self.get_shoot_date(fp, media_type)
            date_str = (
                shoot_date.strftime(
                    getattr(self.config, "folder_structure", {}).get("date_format", "%Y-%m-%d")
                )
                if shoot_date
                else "无日期"
            )
            device = self.get_device(fp, media_type)
            info = MediaInfo(
                path=fp,
                media_type=media_type,
                shoot_date=shoot_date,
                device=device,
                date_str=date_str,
            )
            target_dir = self.build_target_dir(info, target)
            unified_basename = None
            if getattr(self.config, "unified_naming", True):
                w, h = _get_resolution(fp, media_type, getattr(self.config, "use_exiftool", True))
                res_str = f"{w}x{h}" if (w and h) else ""
                fps_str = _get_frame_rate(fp, media_type, getattr(self.config, "use_exiftool", True))
                unified_basename = self._build_unified_basename(device, date_str, res_str, fps_str)
            primary_dest = self.resolve_destination(target_dir, fp, unified_basename)
            if primary_dest is None:
                stats["skip"] += 1
                report["media_skip"].append((str(fp), "已存在"))
                logger.info("超级拷贝 跳过已存在: %s", fp.name)
                continue
            current_op += 1
            def _primary_cb(ph, msg, _c, _t):
                if progress_cb:
                    try:
                        progress_cb(ph, msg, current_op, total_ops)
                    except Exception:
                        pass
            ok, err = self._copy_file_with_hash_verify(fp, primary_dest, dry_run, _primary_cb)
            if progress_cb:
                try:
                    progress_cb("progress", "", current_op, total_ops)
                except Exception:
                    pass
            if not ok:
                stats["fail"] += 1
                report["media_fail"].append((str(fp), err or ""))
                logger.error("超级拷贝 失败 %s: %s", fp.name, err or "")
                continue
            stats["ok"] += 1
            report["media_ok"].append((str(fp), str(primary_dest)))
            copied_paths.add(fp.resolve())

            related = self.find_related_files(fp, media_type)
            for r in related:
                current_op += 1
                r_dest = (
                    self.resolve_destination(target_dir, r, unified_basename)
                    if unified_basename is not None
                    else self.resolve_destination(target_dir, r)
                )
                if r_dest is None:
                    current_op -= 1
                    continue
                def _rel_cb(ph, msg, _c, _t):
                    if progress_cb:
                        try:
                            progress_cb(ph, msg, current_op, total_ops)
                        except Exception:
                            pass
                ok, err = self._copy_file_with_hash_verify(r, r_dest, dry_run, _rel_cb)
                if progress_cb:
                    try:
                        progress_cb("progress", "", current_op, total_ops)
                    except Exception:
                        pass
                if not ok:
                    report["media_fail"].append((str(r), err or ""))
                    logger.warning("超级拷贝 关联文件失败 %s: %s", r.name, err or "")
                else:
                    stats["ok"] += 1
                    report["media_ok"].append((str(r), str(r_dest)))
                    copied_paths.add(r.resolve())

        other_folder = target / "其他文件"
        other_files_list: List[Tuple[Path, Path, Path]] = []
        try:
            for dirpath, _dirnames, filenames in os.walk(str(source_resolved), topdown=True, followlinks=False):
                for name in filenames:
                    f = Path(dirpath) / name
                    try:
                        fres = f.resolve()
                    except OSError:
                        continue
                    if fres in copied_paths:
                        continue
                    if self.should_leave_in_place(f):
                        continue
                    try:
                        rel = f.relative_to(source_resolved)
                    except ValueError:
                        continue
                    dest_file = other_folder / rel
                    other_files_list.append((f, rel, dest_file))
        except (OSError, PermissionError) as e:
            logger.warning("超级拷贝 遍历其他文件时出错: %s", e)

        total_ops += len(other_files_list)
        if progress_cb and other_files_list:
            try:
                progress_cb("progress", "开始拷贝其他文件…", current_op, total_ops)
            except Exception:
                pass

        for f, rel, dest_file in other_files_list:
            current_op += 1
            if progress_cb:
                try:
                    progress_cb("progress", f"其他文件: {rel}", current_op, total_ops)
                except Exception:
                    pass
            if dry_run:
                logger.info("[超级拷贝 试运行] 将拷贝(其他): %s -> %s", f.name, dest_file)
                stats["ok"] += 1
                report["other_ok"].append(str(rel))
                continue
            try:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(f), str(dest_file))
                stats["ok"] += 1
                report["other_ok"].append(str(rel))
                logger.info("超级拷贝 已拷贝(其他): %s", rel)
            except Exception as e:
                report["other_fail"].append((str(rel), str(e)))
                logger.warning("超级拷贝 其他文件失败 %s: %s", rel, e)

        if (
            not dry_run
            and getattr(self.config, "delete_empty_folders", False)
        ):
            n = self._remove_empty_dirs(target)
            if n > 0:
                logger.info("超级拷贝: 已清理 %d 个空文件夹", n)
        logger.info("超级拷贝完成: 成功=%d 失败=%d 跳过=%d", stats["ok"], stats["fail"], stats["skip"])
        stats["report"] = report
        return stats


