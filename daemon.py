#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
点点素材管理大师 - 后台守护进程（Docker/头less 运行）
监控配置的挂载路径（如 /media），发现外部设备后自动将未拷贝的新文件超级拷贝到 NAS 指定目录。
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import List

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
os.chdir(_script_dir)

# Docker：若使用 CONFIG_DIR，确保 data 目录有 device_suffixes.json
def _ensure_data_dir():
    config_dir = os.environ.get("CONFIG_DIR", "").strip()
    if not config_dir:
        return
    d = Path(config_dir)
    d.mkdir(parents=True, exist_ok=True)
    dev_db = d / "device_suffixes.json"
    if not dev_db.exists():
        src = Path(_script_dir) / "device_suffixes.json"
        if src.exists():
            import shutil
            shutil.copy2(str(src), str(dev_db))


_ensure_data_dir()
from media_organizer import Config, MediaOrganizer, get_log_file_path, PROJECT_NAME, __version__

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def _list_mount_candidates(watch_path: Path) -> List[Path]:
    """列出 watch_path 下的一级子目录，视为可能的挂载点。"""
    out = []
    if not watch_path.exists() or not watch_path.is_dir():
        return out
    try:
        for p in watch_path.iterdir():
            if p.is_dir() and not p.name.startswith("."):
                try:
                    p.resolve()
                    out.append(p)
                except OSError:
                    pass
    except OSError as e:
        logger.debug("列出 %s 失败: %s", watch_path, e)
    return out


def run_daemon():
    config = Config()
    ac = getattr(config, "auto_copy", None) or {}
    enabled = ac.get("enabled", False)
    watch_paths = ac.get("watch_paths") or ["/media"]
    target_path = (ac.get("target_path") or "").strip()
    poll_interval = max(15, int(ac.get("poll_interval_sec") or 60))

    if not enabled:
        logger.info("自动拷贝未启用（config.json 中 auto_copy.enabled = true 后生效）")
        while True:
            time.sleep(3600)
        return

    if not target_path:
        logger.error("auto_copy.target_path 未配置，请指定 NAS 上的目标目录")
        sys.exit(1)

    target = Path(target_path)
    if not target.exists():
        try:
            target.mkdir(parents=True, exist_ok=True)
            logger.info("已创建目标目录: %s", target)
        except Exception as e:
            logger.error("无法创建目标目录 %s: %s", target, e)
            sys.exit(1)

    logger.info("%s v%s 守护进程启动，监控路径: %s，目标: %s，间隔 %ds",
                PROJECT_NAME, __version__, watch_paths, target, poll_interval)

    organizer = MediaOrganizer(config)
    while True:
        try:
            for watch_str in watch_paths:
                watch = Path(watch_str)
                for mount in _list_mount_candidates(watch):
                    try:
                        logger.info("检测到设备路径: %s，开始超级拷贝…", mount)
                        stats = organizer.super_copy_and_organize(
                            source=mount,
                            target=target,
                            dry_run=False,
                            progress_cb=None,
                        )
                        logger.info("超级拷贝完成 源=%s 成功=%d 失败=%d 跳过=%d",
                                    mount, stats["ok"], stats["fail"], stats["skip"])
                    except Exception as e:
                        logger.exception("超级拷贝失败 源=%s: %s", mount, e)
        except Exception as e:
            logger.exception("本轮检查异常: %s", e)
        time.sleep(poll_interval)


if __name__ == "__main__":
    run_daemon()
