#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Launch GUI (no console). Use pythonw.exe or double-click."""

import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
os.chdir(script_dir)

try:
    from main import main
    main()
except ImportError:
    try:
        import importlib.util
        gui_path = os.path.join(script_dir, "organizer_gui.py")
        spec = importlib.util.spec_from_file_location("organizer_gui", gui_path)
        gui_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gui_module)
        gui_module.main()
    except Exception as e:
        try:
            import tkinter.messagebox as messagebox
            messagebox.showerror("Start Error", "Failed to start:\n%s" % str(e))
        except Exception:
            pass
        sys.exit(1)
except Exception as e:
    try:
        import tkinter.messagebox as messagebox
        messagebox.showerror("Start Error", "Failed to start:\n%s" % str(e))
    except Exception:
        pass
    sys.exit(1)
