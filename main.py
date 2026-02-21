#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
点点素材管理大师 - 主入口
启动 GUI 界面
"""
import sys
import os

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
os.chdir(_script_dir)

if __name__ == "__main__":
    from organizer_gui import main
    main()
