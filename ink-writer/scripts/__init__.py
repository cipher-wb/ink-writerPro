"""
ink-writer scripts package

This package contains all Python scripts for the ink-writer plugin.
"""

__version__ = "11.0.0"
__author__ = "lcy"

# Expose main modules
from . import security_utils
from . import project_locator
from . import chapter_paths

__all__ = [
    "security_utils",
    "project_locator",
    "chapter_paths",
]
