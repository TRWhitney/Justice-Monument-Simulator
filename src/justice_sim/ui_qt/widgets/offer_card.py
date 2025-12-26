"""Offer card widget for search results."""

from __future__ import annotations

import html
from pathlib import Path
import re
from collections.abc import Sequence

from PySide6 import QtCore, QtGui, QtWidgets

from justice_sim.engine.effects import resolve_expr
from justice_sim.models.offer import JusticeData, OutcomeSpec
from justice_sim.models.state import GameState
from justice_sim.util.assets import resolve_npc_image_path
from justice_sim.util.search import OfferSearchResult


class _WrappingLabel(QtWidgets.QLabel):
    def hasHeightForWidth(self) -> bool:
        return self.wordWrap()

    def heightForWidth(self, width: int) -> int:
        return super().heightForWidth(width)


class OfferCard(QtWidgets.QFrame):
    def __init__(
        self,
        data: JusticeData,
        result: OfferSearchResult,
        state: GameState,
        highlight_terms: Sequence[str] | None = None,
        effect_highlight_terms: Sequence[str] | None = None,
        npc_highlight: str | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data = data
        self._state = state
        self._highlight_terms = list(highlight_terms or [])
        self._effect_highlight_terms = list(effect_highlight_terms or [])
        self._npc_highlight = npc_highlight
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        left_widget = self._build_npc_panel(data, result)
        center_widget = self._build_offer_panel(result)
        right_widget = self._build_effects_panel(result)

        left_widget.setFixedWidth(_NPC_PANEL_WIDTH)
        right_widget.setFixedWidth(_EFFECTS_PANEL_WIDTH)
        left_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        right_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )
        center_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )

        layout.addWidget(left_widget, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addWidget(center_widget, 1, QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addWidget(right_widget, 0, QtCore.Qt.AlignmentFlag.AlignTop)

    def _build_npc_panel(
        self, data: JusticeData, result: OfferSearchResult
    ) -> QtWidgets.QWidget:
        npc = data.npcs_by_id.get(result.offer.npc_id)
        npc_name = npc.name if npc else result.npc_name
        image_label = QtWidgets.QLabel()
        image_label.setFixedSize(64, 64)
        image_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        pixmap = _load_pixmap(resolve_npc_image_path(data, npc) if npc else None)
        if pixmap is not None:
            image_label.setPixmap(
                pixmap.scaled(
                    64,
                    64,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )

        name_label = _WrappingLabel()
        _set_label_text(
            name_label,
            npc_name,
            _merge_terms(self._highlight_terms, [self._npc_highlight]),
        )
        name_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-weight: 600;")

        column = QtWidgets.QVBoxLayout()
        column.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop
        )
        column.addWidget(image_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(name_label)
        column.addStretch(1)

        widget = QtWidgets.QWidget()
        widget.setLayout(column)
        return widget

    def _build_offer_panel(self, result: OfferSearchResult) -> QtWidgets.QWidget:
        title = _WrappingLabel()
        title.setStyleSheet("font-weight: 600;")
        title.setWordWrap(True)
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        _set_label_text(title, result.offer.title, self._highlight_terms)

        text = _WrappingLabel()
        text.setWordWrap(True)
        text.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        _set_label_text(text, result.offer.text, self._highlight_terms)

        column = QtWidgets.QVBoxLayout()
        column.addWidget(title)
        column.addWidget(text)
        column.addStretch(1)

        widget = QtWidgets.QWidget()
        widget.setLayout(column)
        return widget

    def _build_effects_panel(self, result: OfferSearchResult) -> QtWidgets.QWidget:
        approve_icon = _build_action_icon_label(
            _resolve_icon_path("approve.png"), "approve"
        )
        approve_effects = _build_effects_widget(
            result.approve_summary,
            _extract_effect_tokens(result.offer.approve, self._data, self._state),
            "approve",
            _merge_terms(self._highlight_terms, self._effect_highlight_terms),
        )
        reject_icon = _build_action_icon_label(
            _resolve_icon_path("reject.png"), "reject"
        )
        reject_effects = _build_effects_widget(
            result.reject_summary,
            _extract_effect_tokens(result.offer.reject, self._data, self._state),
            "reject",
            _merge_terms(self._highlight_terms, self._effect_highlight_terms),
        )

        stack = QtWidgets.QVBoxLayout()
        stack.setContentsMargins(
            _EFFECTS_PANEL_PADDING,
            _EFFECTS_PANEL_PADDING,
            _EFFECTS_PANEL_PADDING,
            _EFFECTS_PANEL_PADDING,
        )
        stack.setSpacing(_EFFECTS_PANEL_SPACING)
        stack.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        stack.addWidget(approve_icon, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        stack.addWidget(approve_effects)
        stack.addWidget(reject_icon, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        stack.addWidget(reject_effects)
        stack.addStretch(1)

        widget = QtWidgets.QWidget()
        widget.setLayout(stack)
        widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )
        widget.setObjectName("effects_panel")
        return widget


def _build_action_icon_label(icon_path: Path | None, name: str) -> QtWidgets.QLabel:
    icon_label = QtWidgets.QLabel()
    icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    pixmap = _load_pixmap(icon_path)
    if pixmap is not None:
        scaled = pixmap.scaledToWidth(
            _ACTION_ICON_WIDTH, QtCore.Qt.TransformationMode.SmoothTransformation
        )
        icon_label.setPixmap(scaled)
        icon_label.setFixedSize(scaled.size())
    else:
        icon_label.setFixedSize(_ACTION_ICON_WIDTH, _ACTION_ICON_FALLBACK_HEIGHT)
    icon_label.setObjectName(f"action_icon_{name}")
    return icon_label


def _build_effects_widget(
    summary: str,
    tokens: list[tuple[str, str]],
    name: str,
    highlight_terms: Sequence[str] | None = None,
) -> QtWidgets.QWidget:
    label = _WrappingLabel()
    label.setWordWrap(True)
    label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
    label.setTextFormat(QtCore.Qt.TextFormat.RichText)
    label.setText(_format_effects_html(tokens, summary, highlight_terms))
    label.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Expanding,
        QtWidgets.QSizePolicy.Policy.Preferred,
    )
    label.setMinimumWidth(0)
    label.setObjectName(f"action_effects_{name}")
    return label


def _resolve_icon_path(filename: str) -> Path | None:
    repo_root = Path(__file__).resolve().parents[4]
    path = repo_root / "src" / "justice_sim" / "data" / "builtin" / "images" / filename
    return path if path.exists() else None


_RESOURCE_ICONS = {
    "coins": _resolve_icon_path("court_coin.png"),
    "pop": _resolve_icon_path("pop.png"),
    "mh": _resolve_icon_path("mental_health.png"),
    "retirement_chests": _resolve_icon_path("chest.png"),
    "dismissals": _resolve_icon_path("dismissal.png"),
}

_HIGHLIGHT_STYLE = "font-weight: 700; color: #c00000; text-decoration: underline;"
_ACTION_ICON_WIDTH = 180
_ACTION_ICON_FALLBACK_HEIGHT = 32
_RESOURCE_ICON_SIZE = 16
_NPC_PANEL_WIDTH = 140
_EFFECTS_PANEL_WIDTH = 220
_EFFECTS_PANEL_PADDING = 6
_EFFECTS_PANEL_SPACING = 6


def _extract_effect_tokens(
    outcome: OutcomeSpec, data: JusticeData, state: GameState
) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []

    for effect in outcome.effects:
        resource = None
        text = None
        if effect.type == "add_resource":
            resource = effect.params.get("resource")
            amount = effect.params.get("amount")
            if isinstance(amount, (int, float)):
                text = _format_number(float(amount))
            else:
                text = _format_amount_text(amount, data, state)
        elif effect.type == "random_range_resource":
            resource = effect.params.get("resource")
            min_value = effect.params.get("min")
            max_value = effect.params.get("max")
            if min_value is not None and max_value is not None:
                text = _format_range_text(min_value, max_value)
        elif effect.type == "set_resource":
            resource = effect.params.get("resource")
            value = effect.params.get("value")
            text = f"= {_format_amount_text(value, data, state)}"
        elif effect.type == "multiply_resource":
            resource = effect.params.get("resource")
            factor = effect.params.get("factor")
            text = f"x {_format_amount_text(factor, data, state)}"
        elif effect.type == "clamp_resource":
            resource = effect.params.get("resource")
            text = "clamp"
        elif effect.type == "raw_effect":
            raw = effect.params.get("raw")
            if raw:
                text = str(raw)

        if text:
            tokens.append((resource or "", text))

    if outcome.random:
        tokens.append(("", "random outcome"))

    return tokens


def _format_effects_html(
    tokens: list[tuple[str, str]],
    summary: str,
    highlight_terms: Sequence[str] | None = None,
) -> str:
    if not tokens:
        summary_text = summary
        if summary_text.strip().lower() == "no effect":
            summary_text = "No effect"
        return _highlight_text(_capitalize_effect_text(summary_text), highlight_terms)

    parts: list[str] = []
    for resource, text in tokens:
        effect_text = _capitalize_effect_text(str(text))
        effect_html = _highlight_text(effect_text, highlight_terms)
        icon_path = _RESOURCE_ICONS.get(resource) if resource else None
        if icon_path:
            icon_html = (
                f'<img src="{html.escape(str(icon_path))}" '
                f'width="{_RESOURCE_ICON_SIZE}" height="{_RESOURCE_ICON_SIZE}">'
            )
            parts.append(f"{icon_html} {effect_html}")
        else:
            parts.append(effect_html)
    return ", ".join(parts)


def _set_label_text(
    label: QtWidgets.QLabel, text: str, terms: Sequence[str] | None
) -> None:
    label.setTextFormat(QtCore.Qt.TextFormat.RichText)
    label.setText(_highlight_text(text, terms))


def _merge_terms(
    primary_terms: Sequence[str], extra_terms: Sequence[str | None]
) -> list[str]:
    combined = list(primary_terms)
    combined.extend(term for term in extra_terms if term)
    return combined


def _highlight_text(text: str, terms: Sequence[str] | None) -> str:
    if not text:
        return ""
    normalized = _normalize_terms(terms)
    if not normalized:
        return html.escape(text)
    pattern = re.compile(
        "|".join(re.escape(term) for term in normalized), re.IGNORECASE
    )
    parts: list[str] = []
    last_index = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start < last_index:
            continue
        if start > last_index:
            parts.append(html.escape(text[last_index:start]))
        parts.append(
            f'<span style="{_HIGHLIGHT_STYLE}">{html.escape(text[start:end])}</span>'
        )
        last_index = end
    parts.append(html.escape(text[last_index:]))
    return "".join(parts)


def _normalize_terms(terms: Sequence[str] | None) -> list[str]:
    if not terms:
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for term in terms:
        term_text = (term or "").strip()
        if not term_text:
            continue
        key = term_text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(term_text)
    normalized.sort(key=len, reverse=True)
    return normalized


def _capitalize_effect_text(text: str) -> str:
    for index, char in enumerate(text):
        if char.isalpha():
            return text[:index] + char.upper() + text[index + 1 :]
    return text


def _format_number(value: float) -> str:
    sign = "+" if value > 0 else "-" if value < 0 else ""
    abs_value = abs(value)
    return f"{sign} {abs_value:g}".strip()


def _format_amount_text(amount: object, data: JusticeData, state: GameState) -> str:
    value = _resolve_amount_value(amount, data, state)
    if value is not None:
        return _format_number(value)
    if isinstance(amount, dict):
        return str(amount.get("expr", ""))
    if amount is None:
        return "-"
    return str(amount)


def _resolve_amount_value(
    amount: object, data: JusticeData, state: GameState
) -> float | None:
    if amount is None:
        return None
    try:
        return float(resolve_expr(amount, state, data))
    except Exception:
        return None


def _format_range_text(min_value: object, max_value: object) -> str:
    try:
        min_num = float(min_value)
        max_num = float(max_value)
    except (TypeError, ValueError):
        return f"{min_value}-{max_value}"
    sign = "+ " if min_num >= 0 else ""
    return f"{sign}{min_num:g}-{max_num:g}".strip()


def _load_pixmap(path: Path | None) -> QtGui.QPixmap | None:
    if path is None:
        return None
    pixmap = QtGui.QPixmap(str(path))
    if pixmap.isNull():
        return None
    return pixmap
