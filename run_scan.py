#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""点点素材管理大师 - 命令行入口。"""

import argparse
from pathlib import Path

from media_organizer import Config, MediaOrganizer, reset_log_file, PROJECT_NAME


def main():
    parser = argparse.ArgumentParser(description=f"{PROJECT_NAME}：扫描整理 / 超级拷贝")
    parser.add_argument("--source", "-s", type=str, help="扫描整理：源文件夹")
    parser.add_argument("--output", "-o", type=str, help="扫描整理：输出根目录")
    parser.add_argument("--super-copy", action="store_true", help="使用超级拷贝模式（拷贝+整理+哈希校验）")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不实际操作")
    parser.add_argument("--reset-log", action="store_true", help="清空日志")
    args = parser.parse_args()

    if args.reset_log:
        reset_log_file()

    config = Config()

    if args.super_copy:
        if args.source:
            config.super_copy_source = args.source
        if args.output:
            config.super_copy_target = args.output
        config.save_config()
        source = Path(config.super_copy_source) if config.super_copy_source else None
        target = Path(config.super_copy_target) if config.super_copy_target else None
        if not source or not target:
            print("超级拷贝需指定 --source 和 --output（或 config.json 中 super_copy_source / super_copy_target）")
            return 1
        organizer = MediaOrganizer(config)
        stats = organizer.super_copy_and_organize(source=source, target=target, dry_run=args.dry_run)
        print(f"超级拷贝完成: 成功={stats['ok']} 失败={stats['fail']} 跳过={stats['skip']}")
    else:
        if args.source:
            config.source_path = args.source
        if args.output:
            config.output_path = args.output
        config.save_config()
        source = Path(config.source_path) if config.source_path else None
        output = Path(config.output_path) if config.output_path else None
        if not source and not getattr(config, "source_path", ""):
            print("请指定 --source 或在 config.json 中设置 source_path")
            return 1
        organizer = MediaOrganizer(config)
        organizer.scan_and_organize(source=source, output=output, dry_run=args.dry_run)
        print("扫描完成，详见 media_organizer.log")
    return 0


if __name__ == "__main__":
    exit(main() or 0)
