"""跨平台兼容原语集（Windows ↔ POSIX）。

这里只放"原语级"小函数 / context manager；上层业务模块按需 import，避免在多
处复制 ``sys.platform == "win32"`` 分支代码（参考 CLAUDE.md Windows 兼容守则）。
"""
