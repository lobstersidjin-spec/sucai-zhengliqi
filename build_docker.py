#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
点点素材管理大师 - Docker 镜像打包脚本
每次交付时执行此脚本，生成可导入的镜像 tar 包，便于用户直接加载并测试运行。
用法：python build_docker.py
"""

import os
import re
import sys
import subprocess
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
os.chdir(_script_dir)


def get_version() -> str:
    """从 media_organizer.py 读取 __version__"""
    path = _script_dir / "media_organizer.py"
    text = path.read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    if m:
        return m.group(1)
    raise RuntimeError("无法从 media_organizer.py 读取 __version__")


def run(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    print("  ", " ".join(cmd))
    return subprocess.run(cmd, check=check)


def main():
    version = get_version()
    image_name = "sucai-zhengliqi"
    image_tag = f"{image_name}:v{version}"
    tar_name = f"{image_name}-v{version}.tar"

    print(f"点点素材管理大师 - Docker 打包 v{version}")
    print("-" * 50)

    # 1. 构建镜像
    print("\n[1/2] 构建镜像...")
    run(["docker", "build", "--build-arg", f"VERSION={version}", "-t", image_tag, "."])

    # 2. 导出为 tar
    print("\n[2/2] 导出镜像...")
    run(["docker", "save", "-o", tar_name, image_tag])

    print("\n" + "=" * 50)
    print(f"完成！镜像已保存为: {tar_name}")
    print("\n用户导入与运行：")
    print(f"  docker load -i {tar_name}")
    print(f"  # 创建 data 目录并放入 config.json（含 auto_copy 配置）")
    print(f"  docker run -d --name {image_name} -v $(pwd)/data:/data -v /media:/media:ro {image_tag}")
    print("  # 或使用 docker-compose up -d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
