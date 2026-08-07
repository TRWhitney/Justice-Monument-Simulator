"""Log panel widget."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from justice_sim.engine.effects import resolve_expr
from justice_sim.engine.luck import encounter_luck_color
from justice_sim.models.offer import EffectSpec, JusticeData, OfferSpec
from justice_sim.models.state import ActionTrigger, EncounterTrigger, GameState
from justice_sim.persistence.logs import EncounterLuck, SessionLog
from justice_sim.ui_qt.widgets.offer_card import OfferCard
from justice_sim.ui_qt.widgets.resource_delta import format_resource_delta_html
from justice_sim.ui_qt.ui_scale import scale_int
from justice_sim.util.render import summarize_offer
from justice_sim.util.search import OfferSearchResult
from justice_sim.util import expr as expr_util


class LogPanel(QtWidgets.QWidget):
    undo_requested = QtCore.Signal()

    def __init__(
        self, data: JusticeData, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._data = data
        self._ui_scale = 1.0
        self._last_log: SessionLog | None = None
        self._popover = _LogPopover(data, ui_scale=self._ui_scale)
        self.destroyed.connect(self._popover.deleteLater)
        self._hover_item: QtWidgets.QListWidgetItem | None = None
        layout = QtWidgets.QVBoxLayout(self)
        self.log_list = QtWidgets.QListWidget()
        self.log_list.setMouseTracking(True)
        self.log_list.viewport().setMouseTracking(True)
        self.log_list.viewport().installEventFilter(self)
        self.log_list.itemEntered.connect(self._on_item_entered)
        self.undo_button = QtWidgets.QPushButton("Undo")
        layout.addWidget(self.log_list)
        layout.addWidget(self.undo_button)
        self.undo_button.clicked.connect(self.undo_requested.emit)

    def update_log(self, log: SessionLog) -> None:
        self._last_log = log
        self._popover.hide()
        self._hover_item = None
        self.log_list.clear()
        for entry in log.entries:
            item = QtWidgets.QListWidgetItem()
            widget = _LogEntryWidget(entry, ui_scale=self._ui_scale)
            item.setSizeHint(widget.sizeHint())
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entry)
            self.log_list.addItem(item)
            self.log_list.setItemWidget(item, widget)

    def eventFilter(self, source: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if source is self.log_list.viewport():
            if event.type() == QtCore.QEvent.Type.Leave:
                self._hide_popover()
            elif event.type() == QtCore.QEvent.Type.MouseMove:
                if isinstance(event, QtGui.QMouseEvent):
                    self._handle_viewport_mouse_move(event)
        return super().eventFilter(source, event)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        self._hide_popover()
        super().hideEvent(event)

    def _on_item_entered(self, item: QtWidgets.QListWidgetItem) -> None:
        self._show_popover_for_item(item, QtGui.QCursor.pos())

    def _show_popover_for_item(
        self, item: QtWidgets.QListWidgetItem, cursor_pos: QtCore.QPoint
    ) -> None:
        entry = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if entry is None:
            return
        if entry.action in {"skip", "adjust"}:
            self._hover_item = item
            self._ensure_popover_parent()
            self._popover.update_message(
                self._simple_action_title(entry.action),
                self._simple_action_body(entry),
            )
            self._popover.move(self._popover_position(cursor_pos))
            self._popover.show()
            self._popover.raise_()
            return
        offer = self._data.offers_by_id.get(entry.offer_id)
        if not offer:
            return
        approve_summary, reject_summary, dismiss_summary = summarize_offer(
            offer, entry.pre_state, self._data
        )
        if entry.action == "dismiss" and dismiss_summary is None:
            dismiss_summary = reject_summary
        result = OfferSearchResult(
            offer=offer,
            npc_name=self._npc_name(offer.npc_id),
            approve_summary=approve_summary,
            reject_summary=reject_summary,
            dismiss_summary=dismiss_summary,
        )
        self._hover_item = item
        self._ensure_popover_parent()
        extra_effects = self._build_extra_effects(entry, offer)
        self._popover.update_card(
            result,
            entry.pre_state,
            entry.action,
            extra_effects=extra_effects,
            encounter_luck=entry.encounter_luck,
        )
        self._popover.move(self._popover_position(cursor_pos))
        self._popover.show()
        self._popover.raise_()

    def _hide_popover(self) -> None:
        self._popover.hide()
        self._hover_item = None
        self._hover_item = None

    def _handle_viewport_mouse_move(self, event: QtGui.QMouseEvent) -> None:
        item = self.log_list.itemAt(event.pos())
        cursor_pos = event.globalPosition().toPoint()
        if item is None:
            self._hide_popover()
            return
        if item is not self._hover_item:
            self._show_popover_for_item(item, cursor_pos)
            return
        if self._popover.isVisible():
            self._popover.move(self._popover_position(cursor_pos))

    def _popover_position(self, cursor_pos: QtCore.QPoint) -> QtCore.QPoint:
        self._popover.adjustSize()
        size = self._popover.sizeHint()
        height = size.height()
        pos = QtCore.QPoint(cursor_pos.x(), cursor_pos.y() - height)
        window = self.window()
        if window is None:
            return pos
        bounds = window.geometry()
        if pos.y() < bounds.top():
            pos.setY(cursor_pos.y() + 12)
        if pos.x() + size.width() > bounds.right():
            pos.setX(bounds.right() - size.width() + 1)
        if pos.x() < bounds.left():
            pos.setX(bounds.left())
        if pos.y() + size.height() > bounds.bottom():
            pos.setY(bounds.bottom() - size.height() + 1)
        if pos.y() < bounds.top():
            pos.setY(bounds.top())
        return window.mapFromGlobal(pos)

    def _npc_name(self, npc_id: str) -> str:
        npc = self._data.npcs_by_id.get(npc_id)
        return npc.name if npc else npc_id

    def _simple_action_title(self, action: str) -> str:
        if action == "skip":
            return "Skip"
        return "Manual adjustment"

    def _simple_action_body(self, entry) -> str:
        delta_html = format_resource_delta_html(
            entry.pre_state,
            entry.post_state,
            icon_size=scale_int(_BASE_RESOURCE_ICON_SIZE, self._ui_scale, minimum=1),
            action=entry.action,
        )
        case_text = f"Case {entry.pre_state.case_index} → {entry.post_state.case_index}"
        if entry.action == "skip":
            return f"{delta_html}<br>{case_text}"
        return f"{delta_html}<br>State edited manually."

    def _build_extra_effects(
        self, entry, offer: OfferSpec
    ) -> dict[str, list[tuple[str, tuple[EffectSpec, ...], GameState]]]:
        action = entry.action
        pre_state = entry.pre_state
        post_state = entry.post_state
        extras: list[tuple[str, tuple[EffectSpec, ...], GameState]] = []

        if action not in {"skip", "adjust"}:
            if (
                pre_state.required_action
                and action != pre_state.required_action
                and pre_state.required_action_penalty_effects
            ):
                label = f"Penalty (must {pre_state.required_action})"
                extras.append(
                    (label, pre_state.required_action_penalty_effects, pre_state)
                )

            if action == "dismiss" and pre_state.dismissals > 0:
                extras.append(
                    (
                        "Dismissal cost",
                        (
                            EffectSpec(
                                type="add_resource",
                                params={"resource": "dismissals", "amount": -1},
                            ),
                        ),
                        pre_state,
                    )
                )

            for trigger in self._fired_encounter_triggers(pre_state, post_state, offer):
                extras.append(
                    (
                        self._encounter_trigger_label(trigger, offer),
                        trigger.effects,
                        pre_state,
                    )
                )

            for trigger in self._fired_action_triggers(
                pre_state, post_state, offer, action
            ):
                extras.append(
                    (
                        self._action_trigger_label(trigger, offer),
                        trigger.effects,
                        pre_state,
                    )
                )

            if (
                action == "approve"
                and offer.id == self._data.special_rules.harbinger.offer_id
                and self._data.special_rules.harbinger.on_unpaid_effects
            ):
                cost = resolve_expr(
                    {"expr": self._data.special_rules.harbinger.cost_expr},
                    pre_state,
                    self._data,
                )
                if pre_state.coins < cost:
                    extras.append(
                        (
                            "Harbinger unpaid",
                            tuple(self._data.special_rules.harbinger.on_unpaid_effects),
                            pre_state,
                        )
                    )

        next_case = pre_state.case_index + 1
        for event in pre_state.scheduled_events:
            if event.trigger_case_index != next_case:
                continue
            label = "Scheduled effect"
            if event.label:
                label = f"Scheduled: {self._humanize_label(event.label)}"
            extras.append((label, event.effects, post_state))

        return {action: extras} if extras else {}

    def _fired_encounter_triggers(
        self, pre_state: GameState, post_state: GameState, offer: OfferSpec
    ) -> list[EncounterTrigger]:
        fired: list[EncounterTrigger] = []
        for trigger in pre_state.encounter_triggers:
            if not self._encounter_trigger_matches(trigger, offer):
                continue
            if self._trigger_fired(trigger, pre_state, post_state, is_action=False):
                fired.append(trigger)
        return fired

    def _fired_action_triggers(
        self,
        pre_state: GameState,
        post_state: GameState,
        offer: OfferSpec,
        action: str,
    ) -> list[ActionTrigger]:
        fired: list[ActionTrigger] = []
        for trigger in pre_state.action_triggers:
            if not self._action_trigger_matches(trigger, offer, action):
                continue
            if self._trigger_fired(trigger, pre_state, post_state, is_action=True):
                fired.append(trigger)
        return fired

    def _trigger_fired(
        self,
        trigger: ActionTrigger | EncounterTrigger,
        pre_state: GameState,
        post_state: GameState,
        *,
        is_action: bool,
    ) -> bool:
        remaining = trigger.remaining_uses
        if remaining is None or remaining < 0:
            return self._predicate_allows(trigger.when, pre_state)
        post_remaining = self._remaining_uses_after(
            post_state, trigger, is_action=is_action
        )
        if post_remaining is None:
            return True
        return post_remaining < remaining

    def _remaining_uses_after(
        self,
        post_state: GameState,
        trigger: ActionTrigger | EncounterTrigger,
        *,
        is_action: bool,
    ) -> int | None:
        collection = (
            post_state.action_triggers if is_action else post_state.encounter_triggers
        )
        for candidate in collection:
            if is_action:
                if not self._same_action_trigger(
                    candidate,
                    trigger,  # type: ignore[arg-type]
                ):
                    continue
            else:
                if not self._same_encounter_trigger(
                    candidate,
                    trigger,  # type: ignore[arg-type]
                ):
                    continue
            return candidate.remaining_uses
        return None

    def _same_action_trigger(self, left: ActionTrigger, right: ActionTrigger) -> bool:
        return (
            left.action == right.action
            and left.npc_id == right.npc_id
            and left.offer_id == right.offer_id
            and left.when == right.when
            and left.label == right.label
            and left.effects == right.effects
        )

    def _same_encounter_trigger(
        self, left: EncounterTrigger, right: EncounterTrigger
    ) -> bool:
        return (
            left.npc_id == right.npc_id
            and left.offer_id == right.offer_id
            and left.when == right.when
            and left.label == right.label
            and left.effects == right.effects
        )

    def _encounter_trigger_matches(
        self, trigger: EncounterTrigger, offer: OfferSpec
    ) -> bool:
        if trigger.offer_id and trigger.offer_id != offer.id:
            return False
        if trigger.npc_id and trigger.npc_id != offer.npc_id:
            return False
        return True

    def _action_trigger_matches(
        self, trigger: ActionTrigger, offer: OfferSpec, action: str
    ) -> bool:
        if trigger.action not in {"any", action}:
            return False
        if trigger.offer_id and trigger.offer_id != offer.id:
            return False
        if trigger.npc_id and trigger.npc_id != offer.npc_id:
            return False
        return True

    def _encounter_trigger_label(
        self, trigger: EncounterTrigger, offer: OfferSpec
    ) -> str:
        if trigger.label:
            return f"Encounter trigger: {self._humanize_label(trigger.label)}"
        target = self._trigger_target(
            trigger.npc_id, trigger.offer_id, offer, fallback="any encounter"
        )
        if target:
            return f"Encounter trigger: {target}"
        return "Encounter trigger"

    def _action_trigger_label(self, trigger: ActionTrigger, offer: OfferSpec) -> str:
        if trigger.label:
            return f"Action trigger: {self._humanize_label(trigger.label)}"
        action_label = trigger.action if trigger.action != "any" else "any"
        target = self._trigger_target(
            trigger.npc_id, trigger.offer_id, offer, fallback="any offer"
        )
        if target:
            return f"Action trigger: {action_label} @ {target}"
        return f"Action trigger: {action_label}"

    def _trigger_target(
        self,
        npc_id: str | None,
        offer_id: str | None,
        offer: OfferSpec,
        *,
        fallback: str,
    ) -> str:
        if npc_id:
            return self._npc_name(npc_id)
        if offer_id:
            target_offer = self._data.offers_by_id.get(offer_id)
            return target_offer.title if target_offer else offer_id
        return fallback

    def _predicate_allows(self, predicate: str | None, state: GameState) -> bool:
        if not predicate:
            return True
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
        try:
            return expr_util.evaluate_predicate(predicate, ctx)
        except expr_util.ExprError:
            return False

    def _humanize_label(self, value: object) -> str:
        if value is None:
            return ""
        text = str(value).replace("_", " ").replace("-", " ").strip()
        return " ".join(part.capitalize() for part in text.split())

    def _ensure_popover_parent(self) -> None:
        window = self.window()
        if window is None:
            return
        if self._popover.parentWidget() is not window:
            self._popover.setParent(window)

    def set_theme(self, dark: bool) -> None:
        self._popover.set_theme(dark)

    def set_ui_scale(self, scale: float) -> None:
        self._ui_scale = scale
        self._popover.set_ui_scale(scale)
        if self._last_log is not None:
            self.update_log(self._last_log)


class _LogEntryWidget(QtWidgets.QWidget):
    def __init__(
        self, entry, ui_scale: float = 1.0, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.entry = entry
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(
            scale_int(6, ui_scale),
            scale_int(4, ui_scale),
            scale_int(6, ui_scale),
            scale_int(4, ui_scale),
        )
        label = QtWidgets.QLabel(
            format_resource_delta_html(
                entry.pre_state,
                entry.post_state,
                icon_size=scale_int(_BASE_RESOURCE_ICON_SIZE, ui_scale, minimum=1),
                action=entry.action,
            )
        )
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.setMouseTracking(True)


class _LogPopover(QtWidgets.QFrame):
    def __init__(
        self,
        data: JusticeData,
        ui_scale: float = 1.0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ui_scale = ui_scale
        self.apply_window_attributes()
        self._data = data
        self._shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(scale_int(_BASE_SHADOW_BLUR, ui_scale))
        self._shadow.setOffset(0, scale_int(_BASE_SHADOW_OFFSET_Y, ui_scale))
        self.setGraphicsEffect(self._shadow)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.set_theme(False)

    def apply_window_attributes(self) -> None:
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

    def set_theme(self, dark: bool) -> None:
        self._dark = dark
        radius = scale_int(_BASE_POPOVER_RADIUS, self._ui_scale)
        if dark:
            self.setStyleSheet(
                "background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                " stop:0 #2e2e2e, stop:1 #1f1f1f);"
                f"border-radius: {radius}px;"
            )
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 200))
        else:
            self.setStyleSheet(
                "background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                " stop:0 #fff8ee, stop:1 #efe1cc);"
                f"border-radius: {radius}px;"
            )
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 130))

    def update_card(
        self,
        result: OfferSearchResult,
        state,
        action: str,
        extra_effects: dict[str, list[tuple[str, tuple[EffectSpec, ...], GameState]]]
        | None = None,
        encounter_luck: EncounterLuck | None = None,
    ) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        if encounter_luck is not None:
            luck_label = QtWidgets.QLabel(
                _format_encounter_luck_html(encounter_luck.rank, encounter_luck.total)
            )
            luck_label.setObjectName("encounter_luck_label")
            luck_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            luck_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
            luck_label.setStyleSheet("font-weight: 600; padding: 8px 8px 0 8px;")
            self._layout.addWidget(luck_label)
        card = OfferCard(
            self._data,
            result,
            state,
            action_filter=action,
            extra_effects=extra_effects,
            ui_scale=self._ui_scale,
        )
        card.setFixedWidth(scale_int(_LOG_POPOVER_WIDTH, self._ui_scale, minimum=1))
        card.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        card.layout().activate()
        card.adjustSize()
        self._layout.addWidget(card)
        self.adjustSize()

    def update_message(self, title: str, body: str) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        title_label = QtWidgets.QLabel(title)
        title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        title_label.setStyleSheet("font-weight: 600;")
        body_label = QtWidgets.QLabel(body)
        body_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        body_label.setWordWrap(True)
        body_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        body_label.setStyleSheet("padding: 0 8px 8px 8px;")
        self._layout.addWidget(title_label)
        self._layout.addWidget(body_label)
        self.adjustSize()

    def set_ui_scale(self, scale: float) -> None:
        self._ui_scale = scale
        self._shadow.setBlurRadius(scale_int(_BASE_SHADOW_BLUR, scale))
        self._shadow.setOffset(0, scale_int(_BASE_SHADOW_OFFSET_Y, scale))
        self.set_theme(getattr(self, "_dark", False))


_BASE_RESOURCE_ICON_SIZE = 18
_BASE_SHADOW_BLUR = 26
_BASE_SHADOW_OFFSET_Y = 6
_BASE_POPOVER_RADIUS = 10
_LOG_POPOVER_WIDTH = 520


def _format_encounter_luck_html(rank: int, total: int) -> str:
    color = encounter_luck_color(rank, total)
    return (
        "Deal luck: "
        f'<span style="color: {color}; font-weight: 700;">{rank}/{total}</span>'
    )
