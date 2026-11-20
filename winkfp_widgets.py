"""
winkfp_widgets.py
Small Qt helpers shared by the WinKFP sub-tabs.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger("bimmerdaten.winkfp_widgets")


class Worker(QThread):
    """Run a function in a background thread and emit its result."""

    finishedWithResult = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, func: Callable[[], object], parent=None):
        super().__init__(parent)
        self._func = func

    def run(self):
        try:
            self.finishedWithResult.emit(self._func())
        except Exception as exc:
            logger.exception("WinKFP worker failed")
            self.failed.emit(str(exc))
