"""
vin_decoder_tab.py
"VIN decoder" sub-tab of SA Options: shows what can be read from a VIN offline,
plus the vehicle order (FA.TRC) when one is loaded.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from vin_decoder import (
    FaInfo,
    TypeKeyInfo,
    VinReport,
    decode_vin,
    load_type_keys,
    normalize_vin,
)
from winkfp_widgets import COLOR_ERROR, COLOR_MUTED, COLOR_OK, COLOR_WARNING, WINKFP_STYLE, html_page

logger = logging.getLogger("bimmerdaten.vin_decoder_tab")

STATUS_ICON = {"ok": "✓", "warn": "⚠", "error": "✗", "info": ""}
STATUS_COLOR = {"ok": COLOR_OK, "warn": COLOR_WARNING, "error": COLOR_ERROR, "info": "#111111"}


class VinDecoderTab(QWidget):
    """VIN input + decoded report."""

    showSaCodesRequested = pyqtSignal()

    def __init__(
        self,
        daten_folder: str,
        sa_names: Callable[[str], dict[str, str]] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._daten_folder = daten_folder
        self._sa_names = sa_names
        self._type_keys: dict[str, list[TypeKeyInfo]] | None = None
        self._vehicle_vin = ""
        self._fa: FaInfo | None = None
        self._build_ui()
        self._render()

    # --- UI -----------------------------------------------------------------

    def _build_ui(self):
        self.setStyleSheet(WINKFP_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        row = QHBoxLayout()
        row.addWidget(QLabel("VIN:"))
        self.vin_edit = QLineEdit()
        self.vin_edit.setPlaceholderText("Type or paste a 17-character VIN, e.g. WBAAT51060KL12345")
        self.vin_edit.setMaxLength(24)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(11)
        self.vin_edit.setFont(mono)
        self.vin_edit.returnPressed.connect(self.decode)
        self.vin_edit.textEdited.connect(self._on_text_edited)
        row.addWidget(self.vin_edit, 1)

        self.decode_btn = QPushButton("🔎 Decode")
        self.decode_btn.clicked.connect(self.decode)
        row.addWidget(self.decode_btn)

        self.use_vehicle_btn = QPushButton("🚗 Use VIN from vehicle")
        self.use_vehicle_btn.setToolTip("Use the VIN read by NCS Expert (SYSDATEN.TRC next to FA.TRC)")
        self.use_vehicle_btn.clicked.connect(self.use_vehicle_vin)
        self.use_vehicle_btn.setEnabled(False)
        row.addWidget(self.use_vehicle_btn)
        layout.addLayout(row)

        self.source_label = QLabel("")
        self.source_label.setStyleSheet(f"color: {COLOR_MUTED};")
        layout.addWidget(self.source_label)

        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._on_anchor)
        layout.addWidget(self.browser, 1)

    # --- Public -------------------------------------------------------------

    def set_vehicle(self, vin: str, fa: FaInfo | None):
        """Called when SA Options loads FA.TRC. Does not overwrite a VIN the user typed."""
        vin = normalize_vin(vin if vin and vin != "—" else "")
        typed = normalize_vin(self.vin_edit.text())
        user_has_own_vin = bool(typed) and typed != self._vehicle_vin
        self._vehicle_vin = vin
        self._fa = fa
        self.use_vehicle_btn.setEnabled(bool(vin))
        if vin and not user_has_own_vin:
            self.vin_edit.setText(vin)
        self.decode()

    def set_daten_folder(self, folder: str):
        if folder != self._daten_folder:
            self._daten_folder = folder
            self._type_keys = None
            self.decode()

    def use_vehicle_vin(self):
        if self._vehicle_vin:
            self.vin_edit.setText(self._vehicle_vin)
            self.decode()

    def decode(self):
        self._render()

    # --- Internals ----------------------------------------------------------

    def _on_text_edited(self, _text: str):
        self._update_source_label()

    def _update_source_label(self):
        vin = normalize_vin(self.vin_edit.text())
        if not vin:
            self.source_label.setText("")
        elif vin == self._vehicle_vin:
            self.source_label.setText("Source: VIN read from the vehicle by NCS Expert (SYSDATEN.TRC)")
        else:
            self.source_label.setText("Source: VIN typed by you")

    def _keys(self) -> dict[str, list[TypeKeyInfo]]:
        if self._type_keys is None:
            try:
                self._type_keys = load_type_keys(self._daten_folder)
            except Exception:
                logger.exception("Failed to load type keys from %s", self._daten_folder)
                self._type_keys = {}
        return self._type_keys

    def _on_anchor(self, url):
        if url.toString() == "app:sa-codes":
            self.showSaCodesRequested.emit()

    def _render(self):
        self._update_source_label()
        vin = normalize_vin(self.vin_edit.text())
        parts: list[str] = []
        if vin:
            report = decode_vin(vin, self._keys())
            parts.append(self._summary_html(report))
            parts.append(self._fields_html(report))
        else:
            parts.append(
                "<h3>VIN decoder</h3><p>Type or paste a VIN above and press Enter. "
                "When FA.TRC is loaded, the VIN read from the car is filled in automatically.</p>"
            )
        if self._fa:
            parts.append(self._fa_html(self._fa))
        parts.append(self._limits_html())
        self.browser.setHtml(html_page("".join(parts)))

    def _summary_html(self, report: VinReport) -> str:
        out = [f"<h3>VIN <span style='font-family:Consolas;'>{escape(report.vin)}</span></h3>"]
        if report.problems:
            items = "".join(f"<li>{escape(p)}</li>" for p in report.problems)
            out.append(
                f"<p style='color:{COLOR_ERROR};'><b>⚠ This does not look like a valid VIN:</b></p>"
                f"<ul style='color:{COLOR_ERROR};'>{items}</ul>"
            )
        if report.type_matches:
            for match in report.type_matches:
                rows = [
                    ("Model", match.description or "—"),
                    ("Chassis", match.chassis or "—"),
                    ("Body", match.body or "—"),
                    ("Engine", (match.engine or "—") + (f" ({match.cylinders} cylinders)" if match.cylinders else "")),
                    ("Drive side", match.drive_side or "—"),
                    ("Market", ", ".join(match.markets) or "—"),
                    ("Production", match.period or "—"),
                ]
                if match.attributes:
                    rows.append(("Other NCS attributes", ", ".join(match.attributes)))
                rows.append(("Source", f"type key {match.code} in {match.source}"))
                out.append(self._kv_table(rows))
        if self._fa and self._fa.type_key and report.type_key and self._fa.type_key != report.type_key:
            out.append(
                f"<p style='color:{COLOR_WARNING};'>⚠ The type key in this VIN ({escape(report.type_key)}) "
                f"differs from the type key in the loaded FA.TRC ({escape(self._fa.type_key)}). "
                "Either this is a different car, or the VIN / FA stored in the modules was changed.</p>"
            )
        return "".join(out)

    def _fields_html(self, report: VinReport) -> str:
        rows = []
        for f in report.fields:
            icon = STATUS_ICON.get(f.status, "")
            color = STATUS_COLOR.get(f.status, "#111111")
            rows.append(
                "<tr>"
                f"<td>{escape(f.positions)}</td>"
                f"<td style='font-family:Consolas;'><b>{escape(f.chars)}</b></td>"
                f"<td>{escape(f.meaning)}</td>"
                f"<td style='color:{color};'>{icon + ' ' if icon else ''}{escape(f.value)}</td>"
                "</tr>"
            )
        return (
            "<h4>Character by character</h4>"
            "<table border='1' cellspacing='0' cellpadding='4' width='100%'>"
            "<tr><th width='60'>Position</th><th width='80'>Characters</th>"
            "<th width='200'>Meaning</th><th>Value</th></tr>"
            + "".join(rows) + "</table>"
        )

    def _fa_html(self, fa: FaInfo) -> str:
        names = {}
        if self._sa_names and fa.chassis:
            try:
                names = self._sa_names(fa.chassis) or {}
            except Exception:
                logger.exception("SA name lookup failed for %s", fa.chassis)
        type_text = fa.type_key or "—"
        if fa.type_key:
            matches = self._keys().get(fa.type_key, [])
            if matches:
                type_text += " – " + "; ".join(m.title for m in matches)
        rows = [
            ("Chassis", fa.chassis or "—"),
            ("Production date", fa.production_text or "—"),
            ("Type key", type_text),
            ("SA options", f"{len(fa.sa_codes)} (<a href='app:sa-codes'>show in SA codes</a>)"),
        ]
        if fa.e_words:
            rows.append(("Development words (E-words)", ", ".join(fa.e_words)))
        if fa.ho_words:
            rows.append(("Retrofit words (HO-words)", ", ".join(fa.ho_words)))
        if fa.other_codes:
            rows.append(("Other codes", ", ".join(fa.other_codes) + " <i>(probably paint / upholstery)</i>"))
        sa_rows = "".join(
            f"<tr><td style='font-family:Consolas;'>{escape(code)}</td>"
            f"<td>{escape(names.get(code, ''))}</td></tr>"
            for code in fa.sa_codes
        )
        return (
            "<h4>Vehicle order (FA.TRC)</h4>"
            f"<p style='color:{COLOR_MUTED};'>Read from the car by NCS Expert. Unlike the VIN, it lists the options.</p>"
            + self._kv_table(rows, escape_values=False)
            + "<table border='1' cellspacing='0' cellpadding='3' width='100%'>"
            "<tr><th width='60'>SA</th><th>Description</th></tr>" + sa_rows + "</table>"
        )

    @staticmethod
    def _limits_html() -> str:
        return (
            "<h4>What a VIN cannot tell</h4>"
            f"<p style='color:{COLOR_MUTED};'>The VIN does not contain the SA options, paint or upholstery. "
            "Those are in the vehicle order (FA), stored in the car and read by NCS Expert into FA.TRC. "
            "Websites that list options for a VIN look them up in BMW's online database.</p>"
        )

    @staticmethod
    def _kv_table(rows: list[tuple[str, str]], escape_values: bool = True) -> str:
        body = "".join(
            f"<tr><td width='200'><b>{escape(k)}</b></td>"
            f"<td>{escape(v) if escape_values else v}</td></tr>"
            for k, v in rows
        )
        return f"<table cellspacing='0' cellpadding='3' width='100%'>{body}</table>"
