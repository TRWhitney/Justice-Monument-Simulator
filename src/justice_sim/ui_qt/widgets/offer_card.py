"""Offer card widget for search results."""

from __future__ import annotations

import html
import math
from pathlib import Path
import re
from collections.abc import Mapping, Sequence

from PySide6 import QtCore, QtGui, QtWidgets

from justice_sim.engine.effects import (
    MAIN_RESOURCES,
    NON_NEGATIVE_RESOURCES,
    resolve_expr,
    resolve_probability,
)
from justice_sim.models.offer import (
    BernoulliSpec,
    CategoricalSpec,
    EffectSpec,
    JusticeData,
    OutcomeSpec,
)
from justice_sim.models.state import GameState
from justice_sim.util.assets import resolve_npc_image_path
from justice_sim.util import expr as expr_util
from justice_sim.util.search import OfferSearchResult
from justice_sim.ui_qt.ui_scale import scale_int


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
        action_filter: str | None = None,
        title_override: str | None = None,
        title_html_override: str | None = None,
        extra_effects: Mapping[
            str, Sequence[tuple[str, Sequence[EffectSpec], GameState]]
        ]
        | None = None,
        ui_scale: float = 1.0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data = data
        self._state = state
        self._highlight_terms = list(highlight_terms or [])
        self._effect_highlight_terms = list(effect_highlight_terms or [])
        self._npc_highlight = npc_highlight
        self._action_filter = action_filter
        self._title_override = title_override
        self._title_html_override = title_html_override
        self._extra_effects = extra_effects or {}
        self._ui_scale = ui_scale
        self.setObjectName("offer_card")
        self.setProperty("selected", False)
        border_width = self._scaled(2, minimum=1)
        radius = self._scaled(8, minimum=1)
        self.setStyleSheet(
            'QFrame#offer_card[selected="true"] {'
            f" border: {border_width}px solid #6aa9ff;"
            f" border-radius: {radius}px;"
            "}"
        )
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        if action_filter is not None:
            self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            self.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(
            self._scaled(8),
            self._scaled(8),
            self._scaled(8),
            self._scaled(8),
        )
        layout.setSpacing(self._scaled(12))

        left_widget = self._build_npc_panel(data, result)
        center_widget = self._build_offer_panel(result)
        right_widget = self._build_effects_panel(result)

        left_widget.setFixedWidth(self._scaled(_NPC_PANEL_WIDTH))
        right_widget.setFixedWidth(self._scaled(_EFFECTS_PANEL_WIDTH))
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

    def _scaled(self, value: int, *, minimum: int | None = None) -> int:
        return scale_int(value, self._ui_scale, minimum=minimum)

    def _build_npc_panel(
        self, data: JusticeData, result: OfferSearchResult
    ) -> QtWidgets.QWidget:
        npc = data.npcs_by_id.get(result.offer.npc_id)
        npc_name = npc.name if npc else result.npc_name
        image_label = QtWidgets.QLabel()
        image_size = self._scaled(64, minimum=1)
        image_label.setFixedSize(image_size, image_size)
        image_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        pixmap = _load_pixmap(resolve_npc_image_path(data, npc) if npc else None)
        if pixmap is not None:
            image_label.setPixmap(
                pixmap.scaled(
                    image_size,
                    image_size,
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
        title.setObjectName("offer_title_label")
        title.setStyleSheet("font-weight: 600;")
        title.setWordWrap(True)
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        if self._title_html_override is not None and not self._highlight_terms:
            title.setTextFormat(QtCore.Qt.TextFormat.RichText)
            title.setText(self._title_html_override)
        else:
            title_text = self._title_override or result.offer.title
            _set_label_text(title, title_text, self._highlight_terms)

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
        sections: list[tuple[str, OutcomeSpec, str]] = []
        if self._action_filter:
            summary = ""
            if self._action_filter == "approve":
                outcome = result.offer.approve
                summary = result.approve_summary
            elif self._action_filter == "reject":
                outcome = result.offer.reject
                summary = result.reject_summary
            elif self._action_filter == "dismiss":
                outcome = result.offer.dismiss or result.offer.reject
                summary = result.dismiss_summary or result.reject_summary
            elif self._action_filter == "skip":
                outcome = OutcomeSpec(effects=())
                summary = "no effect (skip)"
            else:
                outcome = result.offer.reject
            sections.append((self._action_filter, outcome, summary))
        else:
            sections = [
                ("approve", result.offer.approve, result.approve_summary),
                ("reject", result.offer.reject, result.reject_summary),
            ]

        stack = QtWidgets.QVBoxLayout()
        stack.setContentsMargins(
            self._scaled(_EFFECTS_PANEL_PADDING),
            self._scaled(_EFFECTS_PANEL_PADDING),
            self._scaled(_EFFECTS_PANEL_PADDING),
            self._scaled(_EFFECTS_PANEL_PADDING),
        )
        stack.setSpacing(self._scaled(_EFFECTS_PANEL_SPACING))
        stack.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        action_icon_width = self._scaled(_ACTION_ICON_WIDTH, minimum=1)
        action_icon_fallback = self._scaled(_ACTION_ICON_FALLBACK_HEIGHT, minimum=1)
        resource_icon_size = self._scaled(_RESOURCE_ICON_SIZE, minimum=1)
        for action, outcome, summary in sections:
            icon = _build_action_icon_label(
                _resolve_icon_path(f"{action}.png"),
                action,
                action_icon_width,
                action_icon_fallback,
            )
            tokens = _extract_effect_tokens(outcome, self._data, self._state)
            extra = self._extra_effects.get(action, ())
            if extra:
                tokens = _append_extra_effects(tokens, extra, self._data)
            effects = _build_effects_widget(
                summary,
                tokens,
                action,
                _merge_terms(self._highlight_terms, self._effect_highlight_terms),
                resource_icon_size,
            )
            stack.addWidget(icon, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
            stack.addWidget(effects)
        stack.addStretch(1)

        widget = QtWidgets.QWidget()
        widget.setLayout(stack)
        widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )
        widget.setObjectName("effects_panel")
        return widget


def _build_action_icon_label(
    icon_path: Path | None,
    name: str,
    icon_width: int,
    fallback_height: int,
) -> QtWidgets.QLabel:
    icon_label = QtWidgets.QLabel()
    icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    pixmap = _load_pixmap(icon_path)
    if pixmap is not None:
        scaled = pixmap.scaledToWidth(
            icon_width, QtCore.Qt.TransformationMode.SmoothTransformation
        )
        icon_label.setPixmap(scaled)
        icon_label.setFixedSize(scaled.size())
    else:
        icon_label.setFixedSize(icon_width, fallback_height)
    icon_label.setObjectName(f"action_icon_{name}")
    return icon_label


def _build_effects_widget(
    summary: str,
    tokens: list[tuple[str, str]],
    name: str,
    highlight_terms: Sequence[str] | None = None,
    icon_size: int | None = None,
) -> QtWidgets.QWidget:
    label = _WrappingLabel()
    label.setWordWrap(True)
    label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
    label.setTextFormat(QtCore.Qt.TextFormat.RichText)
    resolved_icon_size = _RESOURCE_ICON_SIZE if icon_size is None else icon_size
    label.setText(
        _format_effects_html(tokens, summary, highlight_terms, resolved_icon_size)
    )
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
_FLAG_DESCRIPTIONS = {
    "reanimated_hand_share": "Reanimated Hand shares steals on future visits",
}
_FLAG_CLEAR_DESCRIPTIONS = {
    "reanimated_hand_share": "End Reanimated Hand sharing steals",
}
_HIDDEN_COUNTERS = {
    "fizarre_drink_approves",
}
_HIDDEN_ENCOUNTER_TRIGGERS = {
    "ghost_scare_pop",
}
_STATUS_DESCRIPTIONS = {
    "ghost_scare": "Scaring legalized: pop -1 each case",
}
_STATUS_CLEAR_DESCRIPTIONS = {
    "ghost_scare": "Scaring ban reinstated",
}


def _extract_effect_tokens(
    outcome: OutcomeSpec, data: JusticeData, state: GameState
) -> list[tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]]:
    tokens: list[
        tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]
    ] = []

    immediate_effects: list[EffectSpec] = []
    deferred_effects: list[EffectSpec] = []
    for effect in outcome.effects:
        if _is_deferred_effect(effect.type):
            deferred_effects.append(effect)
        else:
            immediate_effects.append(effect)

    for effect in immediate_effects:
        if not _effect_applies(effect, state, data):
            continue
        if effect.type == "add_action_trigger":
            tokens.extend(_extract_action_trigger_tokens(effect, data, state, tokens))
            continue
        if effect.type == "add_encounter_trigger":
            label = effect.params.get("label")
            if label in _HIDDEN_ENCOUNTER_TRIGGERS:
                continue
            tokens.extend(
                _extract_encounter_trigger_tokens(effect, data, state, tokens)
            )
            continue
        if effect.type == "schedule_effects":
            tokens.extend(_extract_schedule_tokens(effect, data, state, tokens))
            continue
        if effect.type == "schedule_recurring_effects":
            tokens.extend(_extract_recurring_tokens(effect, data, state, tokens))
            continue
        if effect.type == "require_next_action":
            tokens.extend(_extract_required_action_tokens(effect, data, state, tokens))
            continue

        token = _effect_to_token(effect, data, state)
        if token:
            tokens.append(token)

    for effect in deferred_effects:
        if not _effect_applies(effect, state, data):
            continue
        if effect.type == "add_action_trigger":
            tokens.extend(_extract_action_trigger_tokens(effect, data, state, tokens))
            continue
        if effect.type == "add_encounter_trigger":
            label = effect.params.get("label")
            if label in _HIDDEN_ENCOUNTER_TRIGGERS:
                continue
            tokens.extend(
                _extract_encounter_trigger_tokens(effect, data, state, tokens)
            )
            continue
        if effect.type == "schedule_effects":
            tokens.extend(_extract_schedule_tokens(effect, data, state, tokens))
            continue
        if effect.type == "schedule_recurring_effects":
            tokens.extend(_extract_recurring_tokens(effect, data, state, tokens))
            continue
        if effect.type == "require_next_action":
            tokens.extend(_extract_required_action_tokens(effect, data, state, tokens))
            continue

        token = _effect_to_token(effect, data, state)
        if token:
            tokens.append(token)

    if outcome.random:
        tokens.extend(
            _extract_random_tokens(
                outcome.random, data, state, has_base_effects=bool(tokens)
            )
        )
    return tokens


def _append_extra_effects(
    tokens: list[tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]],
    extras: Sequence[tuple[str, Sequence[EffectSpec], GameState]],
    data: JusticeData,
) -> list[tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]]:
    combined = list(tokens)
    for label, effects, state in extras:
        filtered = [
            effect for effect in effects if _effect_applies(effect, state, data)
        ]
        effect_tokens = _tokens_from_effects(filtered, data, state)
        if not effect_tokens:
            continue
        combined.extend(_prefixed_tokens(f"{label}: ", effect_tokens, combined))
    return combined


def _is_deferred_effect(effect_type: str) -> bool:
    return effect_type in {
        "add_action_trigger",
        "add_encounter_trigger",
        "add_encounter_override",
        "schedule_effects",
        "schedule_recurring_effects",
        "require_next_action",
        "modify_encounter_weights",
        "remove_action_trigger",
        "remove_encounter_trigger",
        "remove_encounter_override",
    }


def _tokens_from_effects(
    effects: Sequence[EffectSpec], data: JusticeData, state: GameState
) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    for effect in effects:
        token = _effect_to_token(effect, data, state)
        if token:
            tokens.append(token)
    return tokens


def _effect_to_token(
    effect: EffectSpec, data: JusticeData, state: GameState
) -> tuple[str, str] | None:
    resource = None
    text = None
    if effect.type == "add_resource":
        resource = effect.params.get("resource")
        amount = effect.params.get("amount")
        if isinstance(amount, (int, float)):
            value = float(amount)
            if resource in MAIN_RESOURCES:
                value = math.ceil(value)
            text = _format_number(value)
        else:
            text = _format_amount_text(amount, data, state, resource)
    elif effect.type == "random_range_resource":
        resource = effect.params.get("resource")
        min_value = effect.params.get("min")
        max_value = effect.params.get("max")
        if min_value is not None and max_value is not None:
            text = _format_range_text(min_value, max_value)
    elif effect.type == "random_exchange":
        take_resource = effect.params.get("take_resource")
        give_resource = effect.params.get("give_resource")
        min_value = effect.params.get("min")
        max_value = effect.params.get("max")
        min_resolved = _resolve_amount_value(min_value, data, state)
        max_resolved = _resolve_amount_value(max_value, data, state)
        if min_resolved is not None and max_resolved is not None:
            range_text = f"{min_resolved:g}-{max_resolved:g}"
        else:
            range_text = "random"
        resource = ""
        text = (
            f"random {range_text} {_humanize_label(take_resource)} "
            f"for equal {_humanize_label(give_resource)}"
        )
    elif effect.type == "set_resource":
        resource = effect.params.get("resource")
        value = effect.params.get("value")
        text = f"= {_format_value_text(value, data, state, resource)}"
    elif effect.type == "multiply_resource":
        resource = effect.params.get("resource")
        factor = effect.params.get("factor")
        factor_value = _resolve_amount_value(factor, data, state)
        if factor_value is not None and factor_value == 0:
            text = "= 0"
        else:
            factor_text = _format_value_text(factor, data, state)
            result = _multiply_result(resource, factor_value, data, state)
            if result is not None:
                text = f"x {factor_text} -> {_format_plain_number(result)}"
            else:
                text = f"x {factor_text}"
    elif effect.type == "clamp_resource":
        resource = effect.params.get("resource")
        min_value = effect.params.get("min")
        max_value = effect.params.get("max")
        if min_value is not None and max_value is not None:
            min_text = _format_value_text(min_value, data, state)
            max_text = _format_value_text(max_value, data, state)
            text = f"clamp {min_text}-{max_text}"
        elif min_value is not None:
            text = f">= {_format_value_text(min_value, data, state)}"
        elif max_value is not None:
            text = f"<= {_format_value_text(max_value, data, state)}"
        else:
            text = "clamp"
    elif effect.type == "swap_resources":
        resource_a = effect.params.get("resource_a")
        resource_b = effect.params.get("resource_b")
        text = f"swap {resource_a}/{resource_b}"
    elif effect.type == "set_resource_floor":
        resource = effect.params.get("resource")
        minimum = effect.params.get("min")
        text = f"floor {_format_value_text(minimum, data, state)}"
    elif effect.type == "clear_resource_floor":
        resource = effect.params.get("resource")
        text = "clear floor"
    elif effect.type == "schedule_effects":
        after_cases = int(effect.params.get("after_cases", 0))
        text = "next case" if after_cases == 1 else f"in {after_cases} cases"
    elif effect.type == "schedule_recurring_effects":
        after_cases = int(effect.params.get("after_cases", 0))
        every_cases = int(effect.params.get("every_cases", 1))
        repeat = int(effect.params.get("repeat", 1))
        cadence = "every case" if every_cases == 1 else f"every {every_cases} cases"
        if repeat > 0:
            cadence = f"{cadence} x{repeat}"
        if after_cases > 0:
            text = f"{cadence} (start {after_cases})"
        else:
            text = cadence
    elif effect.type == "add_encounter_override":
        target = effect.params.get("offer_id") or effect.params.get("npc_id")
        target_name = _format_entity_name(target, data)
        remaining = _format_remaining_uses(effect.params.get("remaining_uses"))
        probability = _format_probability(effect.params.get("probability"), data, state)
        if probability:
            text = f"{probability} chance {target_name}{remaining}"
        else:
            text = f"force {target_name}{remaining}"
    elif effect.type in {"set_counter", "add_counter", "clear_counter"}:
        counter = str(effect.params.get("counter", ""))
        if counter in _HIDDEN_COUNTERS:
            return None
        counter_name = _humanize_label(counter)
        if effect.type == "set_counter":
            value = _format_value_text(effect.params.get("value"), data, state)
            text = f"{counter_name} = {value}"
        elif effect.type == "add_counter":
            value = _format_amount_text(effect.params.get("amount"), data, state)
            text = f"{counter_name} {value}"
        else:
            text = f"clear {counter_name}"
    elif effect.type == "add_status":
        status = str(effect.params.get("status", ""))
        if status in _STATUS_DESCRIPTIONS:
            text = _STATUS_DESCRIPTIONS[status]
        else:
            status_name = _humanize_label(status)
            if effect.duration_cases is not None and effect.duration_cases >= 0:
                text = f"status {status_name} ({effect.duration_cases} cases)"
            else:
                text = f"status {status_name}"
    elif effect.type == "remove_status":
        status = str(effect.params.get("status", ""))
        text = _STATUS_CLEAR_DESCRIPTIONS.get(status)
        if not text:
            text = f"remove {_humanize_label(status)}"
    elif effect.type == "add_flag":
        flag = str(effect.params.get("flag", ""))
        text = _FLAG_DESCRIPTIONS.get(flag) or f"flag {_humanize_label(flag)}"
    elif effect.type == "remove_flag":
        flag = str(effect.params.get("flag", ""))
        text = _FLAG_CLEAR_DESCRIPTIONS.get(flag) or f"clear {_humanize_label(flag)}"
    elif effect.type == "remove_action_trigger":
        label = effect.params.get("label")
        if label:
            text = f"remove trigger {_humanize_label(label)}"
        else:
            text = "remove action trigger"
    elif effect.type == "remove_encounter_trigger":
        label = effect.params.get("label")
        if label in _HIDDEN_ENCOUNTER_TRIGGERS:
            return None
        if label:
            text = f"remove trigger {_humanize_label(label)}"
        else:
            text = "remove encounter trigger"
    elif effect.type == "remove_encounter_override":
        label = effect.params.get("label")
        if label:
            text = f"remove override {_humanize_label(label)}"
        else:
            text = "remove override"
    elif effect.type == "modify_encounter_weights":
        text = "encounter weights updated"
    elif effect.type == "raw_effect":
        raw = effect.params.get("raw")
        if raw:
            text = str(raw)

    if text:
        return (resource or "", text)
    return None


def _extract_action_trigger_tokens(
    effect: EffectSpec,
    data: JusticeData,
    state: GameState,
    existing: Sequence[
        tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]
    ],
) -> list[tuple[str, str, str, str]]:
    params = effect.params
    action = _humanize_label(params.get("action", "any"))
    npc_name = _format_entity_name(params.get("npc_id"), data)
    offer_name = _format_entity_name(params.get("offer_id"), data)
    target = npc_name or offer_name
    remaining = _format_remaining_uses(params.get("remaining_uses"))
    target_suffix = f" @ {target}" if target else ""
    base_prefix = f"On {action}{target_suffix}{remaining}: "
    raw_effects = params.get("effects", [])
    return _prefixed_trigger_effect_tokens(
        base_prefix, raw_effects, data, state, existing
    )


def _extract_encounter_trigger_tokens(
    effect: EffectSpec,
    data: JusticeData,
    state: GameState,
    existing: Sequence[
        tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]
    ],
) -> list[tuple[str, str, str, str]]:
    params = effect.params
    npc_id = params.get("npc_id") or params.get("offer_id")
    target = _format_entity_name(npc_id, data) or "Encounter"
    remaining = _format_remaining_uses(params.get("remaining_uses"))
    base_prefix = f"On {target}{remaining}: "
    raw_effects = params.get("effects", [])
    return _prefixed_trigger_effect_tokens(
        base_prefix, raw_effects, data, state, existing
    )


def _extract_schedule_tokens(
    effect: EffectSpec,
    data: JusticeData,
    state: GameState,
    existing: Sequence[
        tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]
    ],
) -> list[tuple[str, str, str, str]]:
    after_cases = int(effect.params.get("after_cases", 0))
    prefix = "Next case: " if after_cases == 1 else f"In {after_cases} cases: "
    effects = _effects_from_raw(effect.params.get("effects", []))
    return _prefixed_effect_tokens(prefix, effects, data, state, existing)


def _extract_recurring_tokens(
    effect: EffectSpec,
    data: JusticeData,
    state: GameState,
    existing: Sequence[
        tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]
    ],
) -> list[tuple[str, str, str, str]]:
    after_cases = int(effect.params.get("after_cases", 0))
    every_cases = int(effect.params.get("every_cases", 1))
    repeat = int(effect.params.get("repeat", 1))
    effects = _effects_from_raw(effect.params.get("effects", []))
    if every_cases == 1 and repeat > 0:
        case_label = "case" if repeat == 1 else "cases"
        suffix = f" for next {repeat} {case_label}"
        if after_cases > 1:
            suffix = f"{suffix} (starting in {after_cases} cases)"
        effect_tokens = _tokens_from_effects(effects, data, state)
        if not effect_tokens:
            separator = ", " if existing else ""
            return [("", f"next {repeat} {case_label}", separator)]
        tokens: list[tuple[str, str, str]] = []
        for index, (resource, text) in enumerate(effect_tokens):
            separator = ", " if existing or index > 0 else ""
            if index == len(effect_tokens) - 1:
                text = f"{text}{suffix}"
            tokens.append((resource, text, separator))
        return tokens
    cadence = "Every case" if every_cases == 1 else f"Every {every_cases} cases"
    if repeat > 0:
        cadence = f"{cadence} x{repeat}"
    if after_cases > 0:
        prefix = f"{cadence} (start {after_cases}): "
    else:
        prefix = f"{cadence}: "
    return _prefixed_effect_tokens(prefix, effects, data, state, existing)


def _extract_required_action_tokens(
    effect: EffectSpec,
    data: JusticeData,
    state: GameState,
    existing: Sequence[
        tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]
    ],
) -> list[tuple[str, str, str]]:
    action = _humanize_label(effect.params.get("action"))
    penalties = _effects_from_raw(effect.params.get("penalty_effects", []))
    if not penalties:
        text = f"Must {action} next"
        separator = ", " if existing else ""
        return [("", text, separator)]

    penalty_tokens = _tokens_from_effects(penalties, data, state)
    if not penalty_tokens:
        penalty_text = _effects_to_text(penalties, data, state)
        text = f"Must {action} next (or: {penalty_text})"
        separator = ", " if existing else ""
        return [("", text, separator)]

    tokens: list[tuple[str, str, str, str]] = []
    prefix = f"Must {action} next (or: "
    for index, (resource, text) in enumerate(penalty_tokens):
        separator = ", " if existing or index > 0 else ""
        prefix_text = prefix if index == 0 else ""
        if index == len(penalty_tokens) - 1:
            text = f"{text})"
        tokens.append((resource, text, separator, prefix_text))
    return tokens


def _prefixed_effect_tokens(
    prefix: str,
    effects: Sequence[EffectSpec],
    data: JusticeData,
    state: GameState,
    existing: Sequence[
        tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]
    ],
) -> list[tuple[str, str, str, str]]:
    effect_tokens = _tokens_from_effects(effects, data, state)
    if not effect_tokens:
        separator = ", " if existing else ""
        return [("", prefix.rstrip(": ").strip(), separator)]
    tokens: list[tuple[str, str, str, str]] = []
    for index, (resource, text) in enumerate(effect_tokens):
        separator = ", " if existing or index > 0 else ""
        prefix_text = prefix if index == 0 else ""
        tokens.append((resource, text, separator, prefix_text))
    return tokens


def _prefixed_trigger_effect_tokens(
    base_prefix: str,
    raw_effects: Sequence[dict],
    data: JusticeData,
    state: GameState,
    existing: Sequence[
        tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]
    ],
) -> list[tuple[str, str, str, str]]:
    tokens: list[tuple[str, str, str, str]] = []
    groups = _group_effects_by_when(raw_effects)
    base_used = False
    for when_value, group_effects in groups:
        group_tokens = _tokens_for_trigger_group(
            base_prefix if not base_used else "",
            when_value,
            group_effects,
            data,
            state,
            existing=existing or tokens,
        )
        if group_tokens:
            tokens.extend(group_tokens)
            base_used = True
    return tokens


def _tokens_for_trigger_group(
    base_prefix: str,
    when_value: object,
    raw_effects: Sequence[dict],
    data: JusticeData,
    state: GameState,
    existing: Sequence[
        tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]
    ],
) -> list[tuple[str, str, str, str]]:
    primary_effects, cleanup_text = _split_trigger_effects(raw_effects)
    tokens = _tokens_from_effects(primary_effects, data, state)
    if cleanup_text:
        tokens.append(("", cleanup_text))
    if not tokens:
        return []
    prefix = base_prefix
    if when_value:
        condition = _humanize_condition(when_value)
        if prefix:
            prefix = f"{prefix}If {condition}: "
        else:
            prefix = f"If {condition}: "
    return _prefixed_tokens(prefix, tokens, existing)


def _prefixed_tokens(
    prefix: str,
    tokens: Sequence[tuple[str, str]],
    existing: Sequence[
        tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]
    ],
) -> list[tuple[str, str, str, str]]:
    if not tokens:
        separator = ", " if existing else ""
        return [("", prefix.rstrip(": ").strip(), separator, "")]
    result: list[tuple[str, str, str, str]] = []
    for index, (resource, text) in enumerate(tokens):
        separator = ", " if existing or index > 0 else ""
        prefix_text = prefix if index == 0 else ""
        result.append((resource, text, separator, prefix_text))
    return result


def _group_effects_by_when(
    raw_effects: Sequence[dict],
) -> list[tuple[object | None, list[dict]]]:
    groups: list[tuple[str | None, object | None, list[dict]]] = []
    for raw in raw_effects:
        when_value = raw.get("when")
        key = str(when_value) if when_value is not None else None
        for index, (existing_key, _, bucket) in enumerate(groups):
            if existing_key == key:
                bucket.append(raw)
                break
        else:
            groups.append((key, when_value, [raw]))
    return [(when_value, bucket) for _, when_value, bucket in groups]


def _split_trigger_effects(
    raw_effects: Sequence[dict],
) -> tuple[list[EffectSpec], str | None]:
    cleanup_types = {
        "remove_action_trigger",
        "remove_encounter_trigger",
        "remove_encounter_override",
    }
    primary_raw = []
    remove_present = False
    clear_counters: list[str] = []
    for raw in raw_effects:
        effect_type = raw.get("type")
        if effect_type in cleanup_types:
            remove_present = True
            continue
        if effect_type == "clear_counter":
            counter = raw.get("params", {}).get("counter")
            if counter:
                clear_counters.append(str(counter))
            continue
        primary_raw.append(raw)
    cleanup_text = None
    if remove_present:
        cleanup_text = "end deal"
    elif clear_counters:
        if len(clear_counters) == 1:
            cleanup_text = f"clear {_humanize_label(clear_counters[0])}"
        else:
            cleanup_text = "clear counters"
    return _effects_from_raw(primary_raw), cleanup_text


def _effects_from_raw(raw_effects: Sequence[dict]) -> list[EffectSpec]:
    return [
        EffectSpec(
            type=str(raw.get("type")),
            params=dict(raw.get("params", {})),
            when=raw.get("when"),
            duration_cases=raw.get("duration_cases"),
            schedule_after_cases=raw.get("schedule_after_cases"),
            label=raw.get("label"),
        )
        for raw in raw_effects
    ]


def _effects_to_text(
    effects: Sequence[EffectSpec], data: JusticeData, state: GameState
) -> str:
    parts = []
    for resource, text in _tokens_from_effects(effects, data, state):
        if resource:
            parts.append(f"{text} {_humanize_label(resource)}")
        else:
            parts.append(text)
    return ", ".join(parts)


def _extract_random_tokens(
    random_spec: BernoulliSpec | CategoricalSpec,
    data: JusticeData,
    state: GameState,
    has_base_effects: bool,
) -> list[tuple[str, str, str] | tuple[str, str, str, str]]:
    choice_effects: list[tuple[EffectSpec, ...]] = []
    if isinstance(random_spec, BernoulliSpec):
        choice_effects = [random_spec.then_effects, random_spec.else_effects]
    elif isinstance(random_spec, CategoricalSpec):
        choice_effects = [choice.effects for choice in random_spec.choices]

    if not choice_effects:
        prefix = ", " if has_base_effects else ""
        return [("", "random outcome", prefix)]

    choices = []
    for effects in choice_effects:
        tokens = _tokens_from_effects(effects, data, state)
        if not tokens:
            tokens = [("", "no effect")]
        choices.append(tokens)

    tokens_with_separators: list[tuple[str, str, str, str]] = []
    prefix = "Random: " if has_base_effects else ""
    for choice_index, choice_tokens in enumerate(choices):
        for token_index, (resource, text) in enumerate(choice_tokens):
            if choice_index == 0 and token_index == 0:
                separator = ", " if has_base_effects else ""
                prefix_text = prefix
            elif token_index == 0:
                separator = " OR "
                prefix_text = ""
            else:
                separator = ", "
                prefix_text = ""
            tokens_with_separators.append((resource, text, separator, prefix_text))

    return tokens_with_separators


def _format_effects_html(
    tokens: list[tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, str]],
    summary: str,
    highlight_terms: Sequence[str] | None = None,
    icon_size: int = _RESOURCE_ICON_SIZE,
) -> str:
    if not tokens:
        summary_text = summary
        if summary_text.strip().lower() == "no effect":
            summary_text = "No effect"
        return _highlight_text(_capitalize_effect_text(summary_text), highlight_terms)

    parts: list[str] = []
    for index, token in enumerate(tokens):
        if len(token) == 4:
            resource, text, separator, prefix = token
        elif len(token) == 3:
            resource, text, separator = token
            prefix = ""
        else:
            resource, text = token
            separator = ", " if index > 0 else ""
            prefix = ""
        effect_text = _capitalize_effect_text(str(text))
        effect_html = _highlight_text(effect_text, highlight_terms)
        icon_path = _RESOURCE_ICONS.get(resource) if resource else None
        if separator:
            parts.append(html.escape(separator))
        if prefix:
            parts.append(_highlight_text(prefix, highlight_terms))
        if icon_path:
            icon_html = (
                f'<img src="{html.escape(str(icon_path))}" '
                f'width="{icon_size}" height="{icon_size}">'
            )
            parts.append(f"{icon_html} {effect_html}")
        else:
            parts.append(effect_html)
    return "".join(parts)


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


def _format_plain_number(value: float) -> str:
    return f"{value:g}"


def _format_amount_text(
    amount: object, data: JusticeData, state: GameState, resource: object | None = None
) -> str:
    value = _resolve_amount_value(amount, data, state)
    if value is not None:
        if resource in MAIN_RESOURCES:
            value = math.ceil(value)
        return _format_number(value)
    if isinstance(amount, dict):
        return str(amount.get("expr", ""))
    if amount is None:
        return "-"
    return str(amount)


def _format_value_text(
    amount: object, data: JusticeData, state: GameState, resource: object | None = None
) -> str:
    value = _resolve_amount_value(amount, data, state)
    if value is not None:
        if resource in MAIN_RESOURCES:
            value = math.ceil(value)
        return _format_plain_number(value)
    if isinstance(amount, dict):
        return str(amount.get("expr", ""))
    if amount is None:
        return "-"
    return str(amount)


def _multiply_result(
    resource: object,
    factor_value: float | None,
    data: JusticeData,
    state: GameState,
) -> float | None:
    if factor_value is None or resource is None:
        return None
    try:
        current = float(getattr(state, str(resource)))
    except (AttributeError, TypeError, ValueError):
        return None
    value = current * factor_value
    resource_key = str(resource)
    if (
        resource_key in NON_NEGATIVE_RESOURCES
        and data.defaults.debt_mode == "clamp_to_zero"
        and value < 0
    ):
        value = 0.0
    floor = state.resource_floors.get(resource_key)
    if floor is not None and value < floor:
        value = float(floor)
    if resource_key in MAIN_RESOURCES:
        value = math.ceil(value)
    return value


def _resolve_amount_value(
    amount: object, data: JusticeData, state: GameState
) -> float | None:
    if amount is None:
        return None
    try:
        return float(resolve_expr(amount, state, data))
    except Exception:
        return None


def _format_probability(
    spec: object, data: JusticeData, state: GameState
) -> str | None:
    if spec is None:
        return None
    try:
        value = resolve_probability(spec, state, data)
    except Exception:
        return None
    percent = value * 100.0
    if abs(percent - round(percent)) < 1e-6:
        return f"{int(round(percent))}%"
    return f"{percent:.1f}%"


def _format_range_text(min_value: object, max_value: object) -> str:
    try:
        min_num = float(min_value)
        max_num = float(max_value)
    except (TypeError, ValueError):
        return f"{min_value}-{max_value}"
    sign = "+ " if min_num >= 0 else ""
    return f"{sign}{min_num:g}-{max_num:g}".strip()


def _format_entity_name(identifier: object, data: JusticeData) -> str:
    if identifier is None:
        return ""
    key = str(identifier)
    npc = data.npcs_by_id.get(key)
    if npc:
        return npc.name
    offer = data.offers_by_id.get(key)
    if offer:
        return offer.title
    return _humanize_label(key)


def _humanize_label(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in text.split())


def _effect_applies(effect: EffectSpec, state: GameState, data: JusticeData) -> bool:
    if not effect.when:
        return True
    if isinstance(effect.when, str):
        ctx = expr_util.build_predicate_context(
            case_index=state.case_index,
            coins=state.coins,
            pop=state.pop,
            mh=state.mh,
            dismissals=state.dismissals,
            retirement_chests=state.retirement_chests,
            flags=set(state.flags),
            statuses=set(state.statuses.keys()),
            counters=state.counters,
        )
        return expr_util.evaluate_predicate(effect.when, ctx)
    return True


def _humanize_condition(value: object) -> str:
    if value is None:
        return ""
    text = str(value)

    def _replace(match: re.Match) -> str:
        return _humanize_label(match.group(2))

    text = re.sub(r"\b(counters|flags|statuses)\.([A-Za-z0-9_]+)", _replace, text)
    return text.replace("_", " ")


def _format_remaining_uses(remaining: object) -> str:
    if remaining is None:
        return ""
    try:
        remaining_value = int(remaining)
    except (TypeError, ValueError):
        return ""
    if remaining_value <= 0:
        return ""
    if remaining_value == 1:
        return " (once)"
    return f" (x{remaining_value})"


def _load_pixmap(path: Path | None) -> QtGui.QPixmap | None:
    if path is None:
        return None
    pixmap = QtGui.QPixmap(str(path))
    if pixmap.isNull():
        return None
    return pixmap
