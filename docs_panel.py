"""
docs_panel.py
Docs tab: plain-language documentation of the BMW Standard Tools, their files and
BimmerDaten itself. Content lives in docs_content.py.
"""
from __future__ import annotations

import logging
import os
import re
from html import escape, unescape
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QKeySequence, QShortcut, QTextCharFormat, QTextCursor, QTextDocument
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from docs_content import ROOT_KEYS, SECTIONS, TOPICS, TOPICS_BY_ID, DocTopic
from winkfp_widgets import BASE_FONT, COLOR_ERROR, COLOR_INFO, COLOR_MUTED, COLOR_OK, WINKFP_STYLE, style_tree

logger = logging.getLogger("bimmerdaten.docs_panel")

HOME_TOPIC = "overview"
MAX_EXAMPLES = 5

DOC_STYLE = f"""
<style>
body {{ font-family: {BASE_FONT}; font-size: 14px; color: #111111; }}
h2 {{ font-size: 21px; margin-top: 0px; margin-bottom: 2px; color: #000080; }}
h4 {{ font-size: 15px; margin-top: 12px; margin-bottom: 4px; }}
p, li {{ line-height: 135%; }}
td, th {{ font-size: 13px; }}
code {{ font-family: "Consolas", "Courier New", monospace; font-size: 13px; background-color: #eef0f3; color: #1a1a5e; }}
pre {{ font-family: "Consolas", "Courier New", monospace; font-size: 13px; background-color: #f2f2ee; padding: 6px; }}
a {{ color: {COLOR_INFO}; }}
</style>
"""


def _plain(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).lower()


def default_roots() -> dict[str, str]:
    """Best-guess roots used when the main window does not provide better ones."""
    windir = os.environ.get("WINDIR", r"C:\Windows")
    appdata = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "BimmerDaten"
    roots = {
        "EDIABAS": r"C:\EDIABAS",
        "ECU": r"C:\EDIABAS\Ecu",
        "INPA": r"C:\EC-APPS\INPA",
        "NCS": r"C:\NCSEXPER",
        "NFS": r"C:\EC-APPS\NFS",
        "WINDOWS": windir,
        "APPDATA": str(appdata),
    }
    try:
        from winkfp_parser import load_paths

        paths = load_paths()
        roots["NFS"] = str(paths.nfs_root)
        if paths.ecu_dir:
            roots["ECU"] = str(paths.ecu_dir)
            roots["EDIABAS"] = str(Path(paths.ecu_dir).parent)
    except Exception:
        logger.exception("Could not read WinKFP paths for the Docs tab")
    return roots


class DocsPanel(QWidget):
    """Top-level Docs tab."""

    openAppTabRequested = pyqtSignal(str)

    def __init__(self, parent=None, roots: dict[str, str] | None = None):
        super().__init__(parent)
        self._roots = default_roots()
        if roots:
            self.set_roots(roots)
        self._plain = {t.id: _plain(t.title + " " + t.summary + " " + " ".join(t.keywords) + " " + t.body) for t in TOPICS}
        self._titles = {t.id: (t.title + " " + " ".join(t.keywords)).lower() for t in TOPICS}
        self._history: list[str] = []
        self._history_pos = -1
        self._current: str | None = None
        self._items: dict[str, QTreeWidgetItem] = {}
        self._sections: dict[str, QTreeWidgetItem] = {}
        self.setStyleSheet(WINKFP_STYLE)
        self._build_ui()
        self.open_topic(HOME_TOPIC)

    # ------------------------------------------------------------------ setup

    def set_roots(self, roots: dict[str, str]) -> None:
        for key, value in roots.items():
            if key in ROOT_KEYS and value:
                self._roots[key] = str(value)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        # Left: search + topic tree
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Search docs (e.g. KFCONF, 1063, ZB, coding)…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        self.search.returnPressed.connect(self._open_first_match)
        left_layout.addWidget(self.search)

        self.match_label = QLabel()
        self.match_label.setStyleSheet(f"color: {COLOR_MUTED};")
        left_layout.addWidget(self.match_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        style_tree(self.tree)
        self.tree.setUniformRowHeights(False)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        left_layout.addWidget(self.tree, 1)
        self._fill_tree()

        # Right: navigation + page
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        nav = QHBoxLayout()
        self.back_btn = QPushButton("◀ Back")
        self.back_btn.clicked.connect(self.go_back)
        self.forward_btn = QPushButton("Forward ▶")
        self.forward_btn.clicked.connect(self.go_forward)
        self.home_btn = QPushButton("🏠 Start")
        self.home_btn.clicked.connect(lambda: self.open_topic(HOME_TOPIC))
        for button in (self.back_btn, self.forward_btn, self.home_btn):
            nav.addWidget(button)
        self.crumb = QLabel()
        self.crumb.setTextFormat(Qt.TextFormat.PlainText)
        self.crumb.setStyleSheet(f"color: {COLOR_MUTED}; padding-left: 8px;")
        nav.addWidget(self.crumb, 1)
        right_layout.addLayout(nav)

        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.anchorClicked.connect(self._on_anchor)
        self.browser.document().setDocumentMargin(14)
        right_layout.addWidget(self.browser, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 900])
        layout.addWidget(splitter)

        QShortcut(QKeySequence.StandardKey.Find, self, activated=self._focus_search,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence.StandardKey.Back, self, activated=self.go_back,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence.StandardKey.Forward, self, activated=self.go_forward,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def _fill_tree(self) -> None:
        bold = self.tree.font()
        bold.setBold(True)
        for section in SECTIONS:
            section_item = QTreeWidgetItem([section])
            section_item.setFont(0, bold)
            section_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(section_item)
            self._sections[section] = section_item
        for t in TOPICS:
            item = QTreeWidgetItem([unescape(t.title)])
            item.setData(0, Qt.ItemDataRole.UserRole, t.id)
            item.setToolTip(0, t.summary)
            self._sections[t.section].addChild(item)
            self._items[t.id] = item
        for section, item in self._sections.items():
            item.setExpanded(section != "Glossary")
        self.match_label.setText(f"{len(TOPICS)} topics")

    # ------------------------------------------------------------------ search

    def _search_terms(self) -> list[str]:
        return [w for w in self.search.text().lower().split() if w]

    def _matches(self, topic_id: str, terms: list[str]) -> bool:
        text = self._plain[topic_id]
        return all(term in text for term in terms)

    def _rank(self, topic_id: str, terms: list[str]) -> int:
        title = self._titles[topic_id]
        return sum(3 for term in terms if term in title) + sum(self._plain[topic_id].count(term) > 2 for term in terms)

    def _apply_filter(self) -> None:
        terms = self._search_terms()
        shown = 0
        for topic_id, item in self._items.items():
            visible = not terms or self._matches(topic_id, terms)
            item.setHidden(not visible)
            shown += visible
        for section, section_item in self._sections.items():
            any_visible = any(not section_item.child(i).isHidden() for i in range(section_item.childCount()))
            section_item.setHidden(not any_visible)
            section_item.setExpanded(bool(terms) or section != "Glossary")
        if terms:
            self.match_label.setText(f"{shown} matching topic(s) — Enter opens the best match" if shown else "No topic matches")
        else:
            self.match_label.setText(f"{len(TOPICS)} topics")
        if self._current:
            self._highlight()

    def _open_first_match(self) -> None:
        terms = self._search_terms()
        if not terms:
            return
        matches = [t.id for t in TOPICS if self._matches(t.id, terms)]
        if matches:
            best = max(matches, key=lambda tid: self._rank(tid, terms))
            self.open_topic(best)

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _highlight(self) -> None:
        terms = self._search_terms()
        selections = []
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#ffe680"))
        document = self.browser.document()
        first = None
        for term in terms:
            cursor = QTextCursor(document)
            while True:
                cursor = document.find(term, cursor)
                if cursor.isNull():
                    break
                selection = QTextEdit.ExtraSelection()
                selection.cursor = cursor
                selection.format = fmt
                selections.append(selection)
                if first is None or cursor.position() < first.position():
                    first = QTextCursor(cursor)
                if len(selections) > 500:
                    break
        self.browser.setExtraSelections(selections)
        if first is not None:
            cursor = QTextCursor(first)
            cursor.clearSelection()
            self.browser.setTextCursor(cursor)
            self.browser.ensureCursorVisible()

    # ------------------------------------------------------------------ navigation

    def open_topic(self, topic_id: str, *, record: bool = True) -> None:
        topic = TOPICS_BY_ID.get(topic_id)
        if topic is None:
            logger.warning("Unknown docs topic %s", topic_id)
            return
        if record:
            del self._history[self._history_pos + 1:]
            if not self._history or self._history[-1] != topic_id:
                self._history.append(topic_id)
            self._history_pos = len(self._history) - 1
        self._current = topic_id
        self.browser.setHtml(self._render(topic))
        self.browser.verticalScrollBar().setValue(0)
        self.crumb.setText(f"{topic.section}  ›  {unescape(topic.title)}")
        item = self._items.get(topic_id)
        if item is not None and self.tree.currentItem() is not item:
            self.tree.blockSignals(True)
            self.tree.setCurrentItem(item)
            self.tree.blockSignals(False)
        self.back_btn.setEnabled(self._history_pos > 0)
        self.forward_btn.setEnabled(self._history_pos < len(self._history) - 1)
        if self._search_terms():
            self._highlight()

    def go_back(self) -> None:
        if self._history_pos > 0:
            self._history_pos -= 1
            self.open_topic(self._history[self._history_pos], record=False)

    def go_forward(self) -> None:
        if self._history_pos < len(self._history) - 1:
            self._history_pos += 1
            self.open_topic(self._history[self._history_pos], record=False)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        topic_id = item.data(0, Qt.ItemDataRole.UserRole)
        if topic_id:
            self.open_topic(topic_id)
        else:
            item.setExpanded(not item.isExpanded())

    def _on_current_item_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        if current is None:
            return
        topic_id = current.data(0, Qt.ItemDataRole.UserRole)
        if topic_id and topic_id != self._current:
            self.open_topic(topic_id)

    def _on_anchor(self, url: QUrl) -> None:
        target = url.toString()
        scheme, _, rest = target.partition(":")
        if scheme == "doc":
            self.open_topic(rest)
        elif scheme == "app":
            if rest == "docs":
                self.open_topic("bimmerdaten")
            else:
                self.openAppTabRequested.emit(rest)
        elif scheme == "open":
            path = Path(rest)
            if path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        elif target.startswith("#"):
            self.browser.scrollToAnchor(target[1:])
        elif scheme in ("http", "https"):
            QDesktopServices.openUrl(url)

    # ------------------------------------------------------------------ rendering

    def _resolve(self, folder: str) -> Path | None:
        try:
            return Path(folder.format(**self._roots))
        except (KeyError, IndexError):
            return None

    def _locations_html(self, topic: DocTopic) -> str:
        if not topic.locations:
            return ""
        rows = []
        for folder_pattern, glob in topic.locations:
            folder = self._resolve(folder_pattern)
            if folder is None:
                continue
            shown = escape(str(folder if glob == "*" else folder / glob))
            if not folder.is_dir():
                rows.append(
                    f'<tr><td valign=top width="22"><span style="color:{COLOR_ERROR};">✗</span></td>'
                    f"<td><code>{shown}</code><br>{self._muted('folder not found on this PC')}</td></tr>"
                )
                continue
            try:
                matches = sorted((p for p in folder.glob(glob)), key=lambda p: p.name.lower())
            except OSError:
                matches = []
            open_link = f'<a href="open:{escape(str(folder))}">📂 Open folder</a>'
            if matches:
                examples = ", ".join(escape(p.name) for p in matches[:MAX_EXAMPLES])
                more = f" … (+{len(matches) - MAX_EXAMPLES})" if len(matches) > MAX_EXAMPLES else ""
                noun = "item" if glob == "*" else "file"
                status = (
                    f'<span style="color:{COLOR_OK};">✓</span>',
                    f"<b>{len(matches)}</b> {noun}{'s' if len(matches) != 1 else ''}: {examples}{more}",
                )
            else:
                status = (f'<span style="color:{COLOR_ERROR};">✗</span>', "no matching file")
            rows.append(
                f"<tr><td valign=top width=\"22\">{status[0]}</td><td><code>{shown}</code> &nbsp; {open_link}<br>"
                f"{self._muted(status[1])}</td></tr>"
            )
        if not rows:
            return ""
        return (
            '<h4>📍 On this PC</h4>'
            '<table width="100%" cellpadding="4" cellspacing="0" bgcolor="#f6f5f1" '
            'style="border: 1px solid #c8ccd4;">' + "".join(rows) + "</table>"
        )

    @staticmethod
    def _muted(text: str) -> str:
        return f'<span style="color:{COLOR_MUTED};">{text}</span>'

    def _render(self, topic: DocTopic) -> str:
        related = ""
        if topic.related:
            links = " · ".join(
                f'<a href="doc:{rid}">{TOPICS_BY_ID[rid].title}</a>' for rid in topic.related if rid in TOPICS_BY_ID
            )
            related = f'<h4>See also</h4><p>{links}</p>'
        section_topics = [t for t in TOPICS if t.section == topic.section]
        index = section_topics.index(topic)
        prev_link = (
            f'<a href="doc:{section_topics[index - 1].id}">◀ {section_topics[index - 1].title}</a>' if index > 0 else ""
        )
        next_link = (
            f'<a href="doc:{section_topics[index + 1].id}">{section_topics[index + 1].title} ▶</a>'
            if index < len(section_topics) - 1 else ""
        )
        pager = ""
        if prev_link or next_link:
            pager = (
                '<hr><table width="100%"><tr>'
                f'<td align="left">{prev_link}</td><td align="right">{next_link}</td></tr></table>'
            )
        return (
            f"<html><head>{DOC_STYLE}</head><body>"
            f"<h2>{topic.title}</h2>"
            f'<p style="color:{COLOR_MUTED}; margin-top:0px;"><i>{topic.summary}</i></p>'
            f"{topic.body}{self._locations_html(topic)}{related}{pager}"
            "</body></html>"
        )
