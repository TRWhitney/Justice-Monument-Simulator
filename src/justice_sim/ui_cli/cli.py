"""Interactive Rich CLI for Justice Simulator."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import shlex
from typing import Literal

from prompt_toolkit import prompt
from rich.console import Console

from justice_sim.config import load_builtin_data, load_builtin_suggested_rules
from justice_sim.engine.encounter import (
    UniformEncounterModel,
    eligible_harbinger_offers,
    select_encounter,
)
from justice_sim.engine.effects import (
    NON_NEGATIVE_RESOURCES,
    apply_effects,
    resolve_expr,
    resolve_probability,
)
from justice_sim.engine.reducer import (
    ActionNotAllowed,
    apply_action,
    apply_action_with_outcome,
    skip_case,
)
from justice_sim.engine.rng import Rng
from justice_sim.engine.scoring import weights_for_preset
from justice_sim.models.offer import (
    BernoulliSpec,
    CategoricalSpec,
    EffectSpec,
    JusticeData,
    OfferSpec,
    OutcomeSpec,
)
from justice_sim.models.state import ActionTrigger, EncounterTrigger, GameState
from justice_sim.models.suggested_rules import SuggestedRules
from justice_sim.persistence.logs import LogEntry, SessionLog
from justice_sim.persistence.profiles import Profile, load_profile, save_profile
from justice_sim.persistence.runs import RunState, load_run_state, save_run_state
from justice_sim.planner.rollout import (
    PlannerConfig,
    PlannerRecommendation,
    RolloutPlanner,
)
from justice_sim.ui_cli.render import (
    render_log_entries,
    render_log_entry_detail,
    render_offer_detail,
    render_recommendation,
    render_search_results,
    render_state,
)
from justice_sim.util import expr as expr_util
from justice_sim.util.render import summarize_outcome
from justice_sim.util.search import OfferSearchResult, search_offers


@dataclass
class PendingPrompt:
    kind: Literal["choice", "value"]
    title: str
    message: str
    options: tuple[str, ...] = ()
    min_value: int | None = None
    max_value: int | None = None


@dataclass
class _PendingRandomEffect:
    kind: Literal["random_range_resource", "random_exchange"]
    resource: str | None
    min_value: int
    max_value: int
    take_resource: str | None = None
    give_resource: str | None = None
    schedule_after_cases: int | None = None
    label: str | None = None


class ManualOutcomeResolver:
    def __init__(
        self, outcome: OutcomeSpec, state: GameState, data: JusticeData
    ) -> None:
        self._outcome = outcome
        self._data = data
        self._current_state = state
        self._resolved_effects: list[EffectSpec] = []
        self._phase: Literal["base", "random_choice", "random_effects", "done"] = "base"
        self._index = 0
        self._pending_prompt: PendingPrompt | None = None
        self._pending_effect: _PendingRandomEffect | None = None
        self._random_choices: list[dict[str, object]] | None = None
        self._random_effects: tuple[EffectSpec, ...] = ()
        self._random_label: str | None = None
        self._advance()

    @property
    def pending_prompt(self) -> PendingPrompt | None:
        return self._pending_prompt

    @property
    def done(self) -> bool:
        return self._phase == "done"

    @property
    def random_label(self) -> str | None:
        return self._random_label

    def resolved_outcome(self) -> OutcomeSpec:
        return OutcomeSpec(
            effects=tuple(self._resolved_effects),
            random=None,
            notes=self._outcome.notes,
        )

    def provide_choice(self, index: int) -> None:
        if self._pending_prompt is None or self._pending_prompt.kind != "choice":
            raise ValueError("No choice pending")
        choices = self._random_choices or []
        if index < 0 or index >= len(choices):
            raise ValueError("Choice out of range")
        choice = choices[index]
        self._random_label = choice.get("label")  # type: ignore[assignment]
        self._random_effects = choice["effects"]  # type: ignore[assignment]
        self._phase = "random_effects"
        self._index = 0
        self._pending_prompt = None
        self._advance()

    def provide_value(self, value: int) -> None:
        if self._pending_prompt is None or self._pending_prompt.kind != "value":
            raise ValueError("No value pending")
        if self._pending_effect is None:
            raise ValueError("No pending effect")
        pending = self._pending_effect
        if pending.kind == "random_range_resource":
            resolved_effect = EffectSpec(
                type="add_resource",
                params={"resource": pending.resource, "amount": value},
                when=None,
                schedule_after_cases=pending.schedule_after_cases,
                label=pending.label,
            )
            self._resolved_effects.append(resolved_effect)
            self._current_state = apply_effects(
                self._current_state, (resolved_effect,), self._data, None
            )
        else:
            take_effect = EffectSpec(
                type="add_resource",
                params={"resource": pending.take_resource, "amount": -value},
                when=None,
                schedule_after_cases=pending.schedule_after_cases,
                label=pending.label,
            )
            give_effect = EffectSpec(
                type="add_resource",
                params={"resource": pending.give_resource, "amount": value},
                when=None,
                schedule_after_cases=pending.schedule_after_cases,
                label=pending.label,
            )
            self._resolved_effects.extend([take_effect, give_effect])
            self._current_state = apply_effects(
                self._current_state, (take_effect, give_effect), self._data, None
            )
        self._pending_effect = None
        self._pending_prompt = None
        self._advance()

    def _advance(self) -> None:
        while True:
            if self._phase == "base":
                if self._index >= len(self._outcome.effects):
                    if self._outcome.random:
                        self._phase = "random_choice"
                        continue
                    self._phase = "done"
                    return
                effect = self._outcome.effects[self._index]
                self._index += 1
                prompt = self._handle_effect(effect)
                if prompt:
                    self._pending_prompt = prompt
                    return
                continue
            if self._phase == "random_choice":
                if self._random_choices is None:
                    self._random_choices = _build_random_choices(
                        self._outcome.random, self._current_state, self._data
                    )
                options = tuple(
                    str(choice.get("display", "")) for choice in self._random_choices
                )
                self._pending_prompt = PendingPrompt(
                    kind="choice",
                    title="Random outcome",
                    message="Choose outcome:",
                    options=options,
                )
                return
            if self._phase == "random_effects":
                if self._index >= len(self._random_effects):
                    self._phase = "done"
                    return
                effect = self._random_effects[self._index]
                self._index += 1
                prompt = self._handle_effect(effect)
                if prompt:
                    self._pending_prompt = prompt
                    return
                continue
            return

    def _handle_effect(self, effect: EffectSpec) -> PendingPrompt | None:
        if effect.type == "random_range_resource":
            if not _effect_applies(effect, self._current_state):
                return None
            resource = effect.params.get("resource")
            if not resource:
                return None
            min_value = int(effect.params.get("min", 0))
            max_value = int(effect.params.get("max", 0))
            if max_value < min_value:
                max_value = min_value
            if max_value == min_value:
                resolved_effect = EffectSpec(
                    type="add_resource",
                    params={"resource": resource, "amount": min_value},
                    when=None,
                    schedule_after_cases=effect.schedule_after_cases,
                    label=effect.label,
                )
                self._resolved_effects.append(resolved_effect)
                self._current_state = apply_effects(
                    self._current_state, (resolved_effect,), self._data, None
                )
                return None
            self._pending_effect = _PendingRandomEffect(
                kind="random_range_resource",
                resource=str(resource),
                min_value=min_value,
                max_value=max_value,
                schedule_after_cases=effect.schedule_after_cases,
                label=effect.label,
            )
            return PendingPrompt(
                kind="value",
                title="Random outcome",
                message=(
                    f"Choose {_resource_label(resource)} ({min_value}-{max_value})"
                ),
                min_value=min_value,
                max_value=max_value,
            )
        if effect.type == "random_exchange":
            if not _effect_applies(effect, self._current_state):
                return None
            take_resource = effect.params.get("take_resource")
            give_resource = effect.params.get("give_resource")
            if not take_resource or not give_resource:
                return None
            min_value = int(
                resolve_expr(effect.params.get("min"), self._current_state, self._data)
            )
            max_value = int(
                resolve_expr(effect.params.get("max"), self._current_state, self._data)
            )
            if (
                self._data.defaults.debt_mode == "clamp_to_zero"
                and take_resource in NON_NEGATIVE_RESOURCES
            ):
                current_value = int(getattr(self._current_state, take_resource))
                max_value = min(max_value, current_value)
            if max_value < min_value:
                min_value = max_value
            if max_value == min_value:
                take_effect = EffectSpec(
                    type="add_resource",
                    params={"resource": take_resource, "amount": -min_value},
                    when=None,
                    schedule_after_cases=effect.schedule_after_cases,
                    label=effect.label,
                )
                give_effect = EffectSpec(
                    type="add_resource",
                    params={"resource": give_resource, "amount": min_value},
                    when=None,
                    schedule_after_cases=effect.schedule_after_cases,
                    label=effect.label,
                )
                self._resolved_effects.extend([take_effect, give_effect])
                self._current_state = apply_effects(
                    self._current_state, (take_effect, give_effect), self._data, None
                )
                return None
            self._pending_effect = _PendingRandomEffect(
                kind="random_exchange",
                resource=None,
                min_value=min_value,
                max_value=max_value,
                take_resource=str(take_resource),
                give_resource=str(give_resource),
                schedule_after_cases=effect.schedule_after_cases,
                label=effect.label,
            )
            return PendingPrompt(
                kind="value",
                title="Random outcome",
                message=(
                    f"Choose {_resource_label(take_resource)} to trade for "
                    f"{_resource_label(give_resource)} ({min_value}-{max_value})"
                ),
                min_value=min_value,
                max_value=max_value,
            )

        self._resolved_effects.append(effect)
        self._current_state = apply_effects(
            self._current_state, (effect,), self._data, None
        )
        return None


class RunSession:
    def __init__(self, data: JusticeData):
        self.data = data
        self.state = self._build_starting_state()
        self.rng = Rng()
        self.log = SessionLog()

    def reset(self, *, reseed: bool = True) -> None:
        previous_seed = self.rng.seed
        self.state = self._build_starting_state()
        self.log = SessionLog()
        if reseed:
            new_rng = Rng()
            while new_rng.seed == previous_seed:
                new_rng = Rng()
            self.rng = new_rng
        else:
            self.rng = Rng(previous_seed)

    def _build_starting_state(self) -> GameState:
        return GameState(
            case_index=1,
            coins=5,
            pop=3,
            mh=1,
            dismissals=0,
            retirement_chests=0,
        )

    def apply(self, offer: OfferSpec, action: str) -> None:
        pre_state = self.state
        new_state, random_label = apply_action(
            self.state, offer, action, self.data, self.rng
        )
        self.log.record(
            pre_state, offer.id, action, self.rng.state(), new_state, random_label
        )
        self.state = new_state

    def skip(self, offer: OfferSpec | None = None) -> None:
        pre_state = self.state
        new_state = skip_case(self.state, self.data, self.rng)
        offer_id = offer.id if offer else "skip"
        self.log.record(pre_state, offer_id, "skip", self.rng.state(), new_state)
        self.state = new_state

    def apply_with_outcome(
        self,
        offer: OfferSpec,
        action: str,
        outcome: OutcomeSpec,
        random_label: str | None,
    ) -> None:
        pre_state = self.state
        new_state, chosen_label = apply_action_with_outcome(
            self.state,
            offer,
            action,
            outcome,
            self.data,
            self.rng,
            random_label=random_label,
        )
        self.log.record(
            pre_state, offer.id, action, self.rng.state(), new_state, chosen_label
        )
        self.state = new_state

    def undo(self) -> None:
        previous = self.log.undo()
        if previous is not None:
            self.state = previous
            if self.log.entries:
                last_rng = self.log.entries[-1].rng_state
                self.rng = Rng.from_state(last_rng)
            else:
                self.rng = Rng(self.rng.seed)


class CliApp:
    def __init__(
        self,
        data: JusticeData,
        suggested_rules: SuggestedRules,
        *,
        console: Console | None = None,
    ) -> None:
        self.console = console or Console()
        self.data = data
        self.planner = RolloutPlanner.from_defaults(
            data, suggested_rules=suggested_rules
        )
        self.encounter_model = UniformEncounterModel()
        self.session = RunSession(data)
        self.search_results: list[OfferSearchResult] = []
        self.current_offer: OfferSpec | None = None
        self.current_recommendation: PlannerRecommendation | None = None
        self.sim_mode: Literal["full", "mid", "none"] = "mid"
        self.show_all = False
        self.user_query = ""
        self._auto_offer_id: str | None = None
        self._auto_offer_case: int | None = None
        self.pending_prompt: PendingPrompt | None = None
        self._pending_resolution: ManualOutcomeResolver | None = None
        self._pending_action: tuple[OfferSpec, str] | None = None

    def run(self) -> int:
        self.console.print("Justice Monument Simulator (CLI)")
        self.console.print("Type 'help' for commands.")
        while True:
            try:
                line = prompt("command> ").strip()
            except KeyboardInterrupt:
                self.console.print("\nExiting.")
                break
            if not line:
                continue
            if not self.handle_command(line):
                break
        return 0

    def handle_command(self, line: str) -> bool:
        try:
            parts = shlex.split(line)
        except ValueError as exc:
            self.console.print(f"Invalid command: {exc}")
            return True
        if not parts:
            return True
        command = parts[0].lower()
        args = parts[1:]

        if self._pending_resolution and command not in {
            "choose",
            "value",
            "cancel",
            "help",
            "state",
            "status",
        }:
            self.console.print(
                "Resolve the pending random outcome first (choose/value/cancel)."
            )
            return True

        if command in {"quit", "exit"}:
            return False
        if command in {"help", "?"}:
            self._print_help()
            return True
        if command == "state":
            render_state(self.console, self.session.state)
            return True
        if command == "status":
            self._render_status()
            return True
        if command in {"search", "s"}:
            query = " ".join(args)
            self.user_query = query
            self._refresh_results()
            self._render_search_results()
            return True
        if command in {"list", "offers"}:
            if not self.search_results:
                self._refresh_results()
            self._render_search_results()
            return True
        if command in {"show-all", "showall"}:
            self._handle_show_all(args)
            return True
        if command == "adjust":
            self._handle_adjust(args)
            return True
        if command == "select":
            self._handle_select(args)
            return True
        if command in {"offer", "show"}:
            self._show_offer_detail()
            return True
        if command in {"recommend", "rec"}:
            self._show_recommendation()
            return True
        if command in {
            "apply",
            "approve",
            "reject",
            "dismiss",
            "skip",
            "best",
            "a",
            "r",
            "d",
        }:
            self._handle_apply(command, args)
            return True
        if command == "undo":
            self._undo()
            return True
        if command == "log":
            self._handle_log(args)
            return True
        if command == "reset":
            self._reset_run()
            return True
        if command == "import":
            self._handle_import(args)
            return True
        if command == "export":
            self._handle_export(args)
            return True
        if command == "save-profile":
            self._handle_save_profile(args)
            return True
        if command == "load-profile":
            self._handle_load_profile(args)
            return True
        if command == "planner":
            self._handle_planner(args)
            return True
        if command == "sim":
            self._handle_sim(args)
            return True
        if command == "choose":
            self._handle_choose(args)
            return True
        if command == "value":
            self._handle_value(args)
            return True
        if command == "cancel":
            self._handle_cancel()
            return True

        self.console.print("Unknown command. Type 'help' for commands.")
        return True

    def _print_help(self) -> None:
        lines = [
            "state                         Show current resources",
            "status                        Show resources + selection",
            "search <query>                Search offers (#npc, $term)",
            "list                          Show last search results",
            "show-all [on|off|toggle]      Toggle showing ineligible offers",
            "adjust <resource> <delta>     Adjust coins/pop/mh/dismissals/chests",
            "select <#>                    Select offer from results",
            "offer                         Show selected offer details",
            "recommend                     Show planner recommendation",
            "apply <approve|reject|dismiss|skip|best>",
            "approve/reject/dismiss/skip/best   Apply action",
            "undo                          Undo last action",
            "log [show <#>]                Show log or entry details",
            "reset                         Reset run",
            "import <path>                 Import run state",
            "export <path>                 Export run state",
            "save-profile <path>           Save planner profile",
            "load-profile <path>           Load planner profile",
            "planner                       Show planner settings",
            "planner set risk <preset>     Set risk (safe/balanced/greedy)",
            "planner set horizon <n>       Set planner horizon",
            "planner set rollouts <n>      Set rollouts per action",
            "sim [full|mid|none]           Set simulation mode",
            "choose <#>                    Resolve pending random choice",
            "value <n>                     Resolve pending random value",
            "cancel                        Cancel pending action",
            "quit                          Exit",
        ]
        for line in lines:
            self.console.print(line)

    def _render_status(self) -> None:
        render_state(self.console, self.session.state)
        if self.current_offer:
            self.console.print(f"Selected: {self.current_offer.title}")
        else:
            self.console.print("Selected: none")
        self.console.print(f"Sim mode: {self.sim_mode}")
        if self.show_all:
            self.console.print("Show all: on")
        if self._is_game_over():
            reason = self.session.state.end_reason or "No viable actions"
            self.console.print(f"Game over: {reason}")

    def _render_search_results(self) -> None:
        if not self.search_results:
            self.console.print("No matches.")
            return
        render_search_results(self.console, self.search_results)

    def _handle_show_all(self, args: list[str]) -> None:
        if self.sim_mode == "full":
            self.console.print("Show all is unavailable in full sim mode.")
            self.show_all = False
            return
        if not args:
            self.show_all = not self.show_all
        else:
            choice = args[0].lower()
            if choice in {"on", "true", "yes"}:
                self.show_all = True
            elif choice in {"off", "false", "no"}:
                self.show_all = False
            elif choice in {"toggle", "flip"}:
                self.show_all = not self.show_all
            else:
                self.console.print("Usage: show-all [on|off|toggle]")
                return
        self._refresh_results()
        state = "on" if self.show_all else "off"
        self.console.print(f"Show all: {state}")

    def _handle_adjust(self, args: list[str]) -> None:
        if len(args) < 2:
            self.console.print("Usage: adjust <coins|pop|mh|dismissals|chests> <delta>")
            return
        resource = args[0].lower()
        try:
            delta = int(args[1])
        except ValueError:
            self.console.print("Delta must be a number.")
            return
        state = self.session.state
        ended = False
        end_reason = None
        if resource == "coins":
            self.session.state = replace(
                state,
                coins=max(0.0, state.coins + delta),
                ended=ended,
                end_reason=end_reason,
            )
        elif resource == "pop":
            self.session.state = replace(
                state,
                pop=max(0.0, state.pop + delta),
                ended=ended,
                end_reason=end_reason,
            )
        elif resource == "mh":
            self.session.state = replace(
                state,
                mh=max(0.0, state.mh + delta),
                ended=ended,
                end_reason=end_reason,
            )
        elif resource == "dismissals":
            self.session.state = replace(
                state,
                dismissals=max(0.0, state.dismissals + delta),
                ended=ended,
                end_reason=end_reason,
            )
        elif resource in {"chests", "retirement_chests"}:
            self.session.state = replace(
                state,
                retirement_chests=max(0.0, state.retirement_chests + delta),
                ended=ended,
                end_reason=end_reason,
            )
        else:
            self.console.print("Usage: adjust <coins|pop|mh|dismissals|chests> <delta>")
            return
        self.session.log.record_manual_adjust(
            state, self.session.state, self.session.rng.state()
        )
        self.current_recommendation = None
        self._refresh_results(preserve_selection=True)
        self._update_recommendation()
        self.console.print(f"Adjusted {resource} by {delta}.")

    def _handle_select(self, args: list[str]) -> None:
        if not args or not args[0].isdigit():
            self.console.print("Usage: select <#>")
            return
        if not self.search_results:
            self.console.print("No search results. Use 'search' first.")
            return
        index = int(args[0]) - 1
        if index < 0 or index >= len(self.search_results):
            self.console.print("Selection out of range.")
            return
        self.current_offer = self.search_results[index].offer
        self.console.print(f"Selected: {self.current_offer.title}")
        self._update_recommendation()
        self._show_offer_detail()
        if self.current_recommendation:
            render_recommendation(self.console, self.current_recommendation)

    def _show_offer_detail(self) -> None:
        if not self.current_offer:
            self.console.print("No offer selected.")
            return
        render_offer_detail(
            self.console, self.data, self.current_offer, self.session.state
        )

    def _show_recommendation(self) -> None:
        if self.sim_mode == "none":
            self.console.print("Recommendations disabled in sim mode 'none'.")
            return
        if not self.current_offer:
            self.console.print("Select an offer first.")
            return
        if self.current_recommendation is None:
            self._update_recommendation()
        if self.current_recommendation is None:
            self.console.print("No recommendation available.")
            return
        render_recommendation(self.console, self.current_recommendation)

    def _handle_apply(self, command: str, args: list[str]) -> None:
        action = None
        if command in {"approve", "a"}:
            action = "approve"
        elif command in {"reject", "r"}:
            action = "reject"
        elif command in {"dismiss", "d"}:
            action = "dismiss"
        elif command == "skip":
            action = "skip"
        elif command == "best":
            action = "best"
        elif command == "apply" and args:
            action = args[0].lower()
        if action is None:
            self.console.print("Usage: apply <approve|reject|dismiss|skip|best>")
            return
        if action == "best":
            best = self._recommended_action()
            if not best:
                self.console.print("No recommendation yet.")
                return
            action = best
        if action == "skip":
            self._apply_skip()
            return
        self._apply_action(action)

    def _apply_action(self, action: str) -> None:
        if not self.current_offer:
            self.console.print("Select an offer first.")
            return
        if self._is_game_over():
            self.console.print("Game over. No viable actions.")
            return
        pre_state = self.session.state
        try:
            if self.sim_mode == "full":
                self.session.apply(self.current_offer, action)
            else:
                outcome = _select_outcome(self.current_offer, action)
                resolver = ManualOutcomeResolver(outcome, self.session.state, self.data)
                if not resolver.done:
                    self._pending_resolution = resolver
                    self._pending_action = (self.current_offer, action)
                    self.pending_prompt = resolver.pending_prompt
                    self._show_pending_prompt()
                    return
                self.session.apply_with_outcome(
                    self.current_offer,
                    action,
                    resolver.resolved_outcome(),
                    resolver.random_label,
                )
        except ActionNotAllowed as exc:
            self.console.print(f"Action failed: {exc}")
            return
        self._after_action(pre_state, action=action)

    def _apply_skip(self) -> None:
        if self._is_game_over():
            self.console.print("Game over. No viable actions.")
            return
        pre_state = self.session.state
        try:
            self.session.skip(self.current_offer)
        except ActionNotAllowed as exc:
            self.console.print(f"Skip failed: {exc}")
            return
        self._after_action(pre_state, action="skip")

    def _after_action(self, pre_state: GameState, *, action: str | None = None) -> None:
        self.console.print(
            f"Applied. Delta: {self._format_delta(pre_state, self.session.state, action=action)}"
        )
        self.current_recommendation = None
        self._refresh_results(preserve_selection=True)
        self._update_recommendation()
        if self._is_game_over():
            reason = self.session.state.end_reason or "No viable actions"
            self.console.print(f"Game over: {reason}")

    def _undo(self) -> None:
        if self._pending_resolution:
            self.console.print("Resolve the pending action before undoing.")
            return
        if not self.session.log.entries:
            self.console.print("Nothing to undo.")
            return
        self.session.undo()
        self.current_recommendation = None
        self._refresh_results(preserve_selection=True)
        self._update_recommendation()
        self.console.print("Undid last action.")

    def _handle_log(self, args: list[str]) -> None:
        if not self.session.log.entries:
            self.console.print("Log is empty.")
            return
        if args and args[0] == "show":
            if len(args) < 2 or not args[1].isdigit():
                self.console.print("Usage: log show <#>")
                return
            index = int(args[1]) - 1
            if index < 0 or index >= len(self.session.log.entries):
                self.console.print("Log entry out of range.")
                return
            entry = self.session.log.entries[index]
            render_log_entry_detail(self.console, entry, self.data)
            extras = _build_extra_effects(entry, self.data)
            for label, effects, state in extras:
                summary = summarize_outcome(
                    OutcomeSpec(effects=effects), state, self.data
                )
                self.console.print(f"{label}: {summary}")
            return
        render_log_entries(self.console, self.session.log, self.data)

    def _reset_run(self) -> None:
        self.session.reset(reseed=True)
        self.current_offer = None
        self.current_recommendation = None
        self._auto_offer_id = None
        self._auto_offer_case = None
        self._pending_resolution = None
        self._pending_action = None
        self.pending_prompt = None
        self._refresh_results(preserve_selection=False)
        self.console.print("Run reset.")

    def _handle_import(self, args: list[str]) -> None:
        if not args:
            self.console.print("Usage: import <path>")
            return
        path = Path(args[0]).expanduser()
        loaded = load_run_state(path)
        self.session.state = loaded.state
        self.session.rng = Rng.from_state(loaded.rng_state)
        self.session.log = SessionLog.from_list(loaded.log)
        self.current_recommendation = None
        self._refresh_results(preserve_selection=True)
        self.console.print(f"Imported run state from {path}")

    def _handle_export(self, args: list[str]) -> None:
        if not args:
            self.console.print("Usage: export <path>")
            return
        path = Path(args[0]).expanduser()
        run_state = RunState(
            version="run_state_v1",
            state=self.session.state,
            rng_state=self.session.rng.state(),
            log=self.session.log.to_list(),
        )
        save_run_state(path, run_state)
        self.console.print(f"Exported run state to {path}")

    def _handle_save_profile(self, args: list[str]) -> None:
        if not args:
            self.console.print("Usage: save-profile <path>")
            return
        path = Path(args[0]).expanduser()
        profile = Profile(
            version="profile_v1", planner_settings=self.planner.config.__dict__
        )
        save_profile(path, profile)
        self.console.print(f"Saved profile to {path}")

    def _handle_load_profile(self, args: list[str]) -> None:
        if not args:
            self.console.print("Usage: load-profile <path>")
            return
        path = Path(args[0]).expanduser()
        profile = load_profile(path)
        if profile.planner_settings:
            self.planner.config = PlannerConfig(**profile.planner_settings)
            self.planner.weights = weights_for_preset(self.planner.config.risk_preset)
            self.planner.reset_cache()
            self.current_recommendation = None
        self.console.print(f"Loaded profile from {path}")

    def _handle_planner(self, args: list[str]) -> None:
        if not args:
            cfg = self.planner.config
            self.console.print(
                f"Planner: risk={cfg.risk_preset}, horizon={cfg.horizon_cases}, "
                f"rollouts={cfg.rollouts_per_action}"
            )
            return
        if len(args) < 3 or args[0] != "set":
            self.console.print("Usage: planner set <risk|horizon|rollouts> <value>")
            return
        key = args[1]
        value = args[2]
        cfg = self.planner.config
        if key == "risk":
            if value not in {"safe", "balanced", "greedy"}:
                self.console.print("Risk must be safe, balanced, or greedy.")
                return
            cfg = PlannerConfig(
                horizon_cases=cfg.horizon_cases,
                rollouts_per_action=cfg.rollouts_per_action,
                adaptive_rollouts=cfg.adaptive_rollouts,
                adaptive_rollouts_max=cfg.adaptive_rollouts_max,
                risk_preset=value,
            )
        elif key == "horizon":
            if not value.isdigit():
                self.console.print("Horizon must be a number.")
                return
            cfg = PlannerConfig(
                horizon_cases=int(value),
                rollouts_per_action=cfg.rollouts_per_action,
                adaptive_rollouts=cfg.adaptive_rollouts,
                adaptive_rollouts_max=cfg.adaptive_rollouts_max,
                risk_preset=cfg.risk_preset,
            )
        elif key == "rollouts":
            if not value.isdigit():
                self.console.print("Rollouts must be a number.")
                return
            cfg = PlannerConfig(
                horizon_cases=cfg.horizon_cases,
                rollouts_per_action=int(value),
                adaptive_rollouts=cfg.adaptive_rollouts,
                adaptive_rollouts_max=cfg.adaptive_rollouts_max,
                risk_preset=cfg.risk_preset,
            )
        else:
            self.console.print("Usage: planner set <risk|horizon|rollouts> <value>")
            return
        self.planner.config = cfg
        self.planner.weights = weights_for_preset(cfg.risk_preset)
        self.planner.reset_cache()
        self.current_recommendation = None
        self._update_recommendation()
        self.console.print("Planner settings updated.")

    def _handle_sim(self, args: list[str]) -> None:
        if not args:
            self.console.print(f"Sim mode: {self.sim_mode}")
            return
        mode = args[0].lower()
        if mode == "mode" and len(args) > 1:
            mode = args[1].lower()
        if mode not in {"full", "mid", "none"}:
            self.console.print("Usage: sim [full|mid|none]")
            return
        previous = self.sim_mode
        if previous == mode:
            self.console.print(f"Sim mode: {self.sim_mode}")
            return
        self.sim_mode = mode  # type: ignore[assignment]
        if previous == "full" and mode != "full":
            self._auto_offer_id = None
            self._auto_offer_case = None
        if mode == "full":
            self.show_all = False
        if mode == "none":
            self.current_recommendation = None
        else:
            self.current_recommendation = None
        self._refresh_results(preserve_selection=True)
        self._update_recommendation()
        self.console.print(f"Sim mode: {self.sim_mode}")

    def _handle_choose(self, args: list[str]) -> None:
        if not self._pending_resolution or not self.pending_prompt:
            self.console.print("No pending choice.")
            return
        if not args or not args[0].isdigit():
            self.console.print("Usage: choose <#>")
            return
        index = int(args[0]) - 1
        try:
            self._pending_resolution.provide_choice(index)
        except ValueError as exc:
            self.console.print(str(exc))
            return
        self._continue_pending_action()

    def _handle_value(self, args: list[str]) -> None:
        if not self._pending_resolution or not self.pending_prompt:
            self.console.print("No pending value.")
            return
        if not args:
            self.console.print("Usage: value <n>")
            return
        try:
            value = int(args[0])
        except ValueError:
            self.console.print("Value must be a number.")
            return
        prompt = self.pending_prompt
        if prompt.min_value is not None and value < prompt.min_value:
            self.console.print("Value below minimum.")
            return
        if prompt.max_value is not None and value > prompt.max_value:
            self.console.print("Value above maximum.")
            return
        try:
            self._pending_resolution.provide_value(value)
        except ValueError as exc:
            self.console.print(str(exc))
            return
        self._continue_pending_action()

    def _handle_cancel(self) -> None:
        if not self._pending_resolution:
            self.console.print("No pending action.")
            return
        self._pending_resolution = None
        self._pending_action = None
        self.pending_prompt = None
        self.console.print("Pending action cancelled.")

    def _continue_pending_action(self) -> None:
        if not self._pending_resolution:
            return
        self.pending_prompt = self._pending_resolution.pending_prompt
        if self._pending_resolution.done:
            offer_action = self._pending_action
            resolver = self._pending_resolution
            self._pending_resolution = None
            self._pending_action = None
            self.pending_prompt = None
            if not offer_action:
                self.console.print("Pending action missing.")
                return
            offer, action = offer_action
            pre_state = self.session.state
            try:
                self.session.apply_with_outcome(
                    offer,
                    action,
                    resolver.resolved_outcome(),
                    resolver.random_label,
                )
            except ActionNotAllowed as exc:
                self.console.print(f"Action failed: {exc}")
                return
            self._after_action(pre_state, action=action)
            return
        self._show_pending_prompt()

    def _show_pending_prompt(self) -> None:
        prompt = self.pending_prompt
        if not prompt:
            return
        self.console.print(prompt.title)
        self.console.print(prompt.message)
        if prompt.kind == "choice":
            for idx, option in enumerate(prompt.options, start=1):
                self.console.print(f"  {idx}. {option}")
        else:
            self.console.print(
                f"Enter value {prompt.min_value}-{prompt.max_value} with 'value <n>'."
            )

    def _update_recommendation(self) -> None:
        if self.sim_mode == "none" or not self.current_offer or self._is_game_over():
            self.current_recommendation = None
            return
        self.current_recommendation = self.planner.recommend(
            self.session.state, self.current_offer
        )

    def _recommended_action(self) -> str | None:
        if self.current_recommendation:
            return self.current_recommendation.best_action
        return None

    def _refresh_results(self, *, preserve_selection: bool = True) -> None:
        self._sync_auto_offer()
        effective_query = self._effective_query()
        eligible_ids = self._eligible_offer_ids()
        if self.show_all and not self._is_offer_locked():
            eligible_ids = None
        self.search_results = search_offers(
            effective_query,
            self.data,
            self.session.state,
            eligible_offer_ids=eligible_ids,
        )
        if not preserve_selection:
            self.current_offer = None
            return
        if self._auto_offer_id:
            self.current_offer = self._offer_by_id(self._auto_offer_id)
            return
        forced_offer = self._forced_offer_id()
        if forced_offer:
            self.current_offer = self._offer_by_id(forced_offer)
            return
        override_ids = self._forced_override_offer_ids()
        if override_ids:
            self.current_offer = self._offer_by_id(override_ids[0])
            return
        if self.current_offer:
            if not any(
                result.offer.id == self.current_offer.id
                for result in self.search_results
            ):
                self.current_offer = None

    def _sync_auto_offer(self) -> None:
        if self.sim_mode != "full":
            return
        if self.session.state.ended:
            self._auto_offer_id = None
            self._auto_offer_case = None
            return
        case_index = self.session.state.case_index
        if self._auto_offer_case == case_index and self._auto_offer_id:
            return
        offer_id = select_encounter(
            self.session.state, self.data, self.encounter_model, self.session.rng
        )
        self._auto_offer_id = offer_id
        self._auto_offer_case = case_index

    def _eligible_offer_ids(self) -> set[str] | None:
        if self._auto_offer_id:
            return {self._auto_offer_id}
        forced_offer = self._forced_offer_id()
        if forced_offer:
            return {forced_offer}
        override_ids = self._forced_override_offer_ids()
        if override_ids:
            return set(override_ids)
        if self._should_force_harbinger():
            eligible = set(eligible_harbinger_offers(self.session.state, self.data))
            grateful_rule = self.data.special_rules.gratefulbinger
            if grateful_rule:
                eligible.add(grateful_rule.offer_id)
            return eligible
        return set(self.encounter_model.eligible_offers(self.session.state, self.data))

    def _forced_offer_id(self) -> str | None:
        for forced in self.session.state.forced_encounters:
            if forced.trigger_case_index == self.session.state.case_index:
                return forced.offer_id
        return None

    def _forced_override_info(self) -> tuple[list[str], str | None]:
        if self.session.state.ended:
            return ([], None)
        harbinger_case = self._should_force_harbinger()
        eligible_ids = set(
            self.encounter_model.eligible_offers(self.session.state, self.data)
        )
        ordered = sorted(
            enumerate(self.session.state.encounter_overrides),
            key=lambda item: (-item[1].priority, item[0]),
        )
        for _, override in ordered:
            if harbinger_case and not override.allow_harbinger:
                continue
            if override.probability is not None:
                try:
                    probability = resolve_probability(
                        override.probability, self.session.state, self.data
                    )
                except Exception:
                    continue
                if probability < 1:
                    return ([], None)
            if override.offer_id and override.offer_id in eligible_ids:
                return ([override.offer_id], "offer")
            if override.npc_id:
                offers = [
                    offer.id
                    for offer in self.data.offers
                    if offer.npc_id == override.npc_id and offer.id in eligible_ids
                ]
                if offers:
                    return (offers, "npc")
        return ([], None)

    def _forced_override_offer_ids(self) -> list[str]:
        return self._forced_override_info()[0]

    def _forced_override_scope(self) -> str | None:
        return self._forced_override_info()[1]

    def _should_force_harbinger(self) -> bool:
        if self.session.state.ended:
            return False
        modulus = self.data.special_rules.harbinger.cadence_modulus
        if modulus <= 0:
            return False
        return self.session.state.case_index % modulus == 0

    def _is_offer_locked(self) -> bool:
        if self._auto_offer_id or self._forced_offer_id():
            return True
        return self._forced_override_scope() == "offer"

    def _forced_filter_query(self) -> str | None:
        if self._auto_offer_id:
            return self._query_for_offer_id(self._auto_offer_id)
        forced_offer = self._forced_offer_id()
        if forced_offer:
            return self._query_for_offer_id(forced_offer)
        override_ids = self._forced_override_offer_ids()
        if override_ids:
            return self._query_for_offer_id(override_ids[0])
        if self._should_force_harbinger():
            return "#binger"
        return None

    def _query_for_offer_id(self, offer_id: str) -> str:
        offer = self.data.offers_by_id.get(offer_id)
        if not offer:
            return ""
        return f"#{offer.npc_id}"

    def _effective_query(self) -> str:
        forced = self._forced_filter_query()
        if forced:
            return forced
        return self.user_query

    def _offer_by_id(self, offer_id: str) -> OfferSpec | None:
        return self.data.offers_by_id.get(offer_id)

    def _is_game_over(self) -> bool:
        if self.session.state.mh <= 0:
            return True
        if not self.current_offer:
            return False
        actions = list(self.current_offer.actions_available)
        if not actions:
            return True
        return not any(self._action_survives(action) for action in actions)

    def _action_survives(self, action: str) -> bool:
        try:
            preview_state, _ = apply_action(
                self.session.state, self.current_offer, action, self.data, Rng(0)
            )
        except ActionNotAllowed:
            return False
        return preview_state.mh > 0

    def _format_delta(
        self, before: GameState, after: GameState, *, action: str | None = None
    ) -> str:
        deltas = {
            "coins": after.coins - before.coins,
            "pop": after.pop - before.pop,
            "mh": after.mh - before.mh,
            "dismissals": after.dismissals - before.dismissals,
            "retirement_chests": after.retirement_chests - before.retirement_chests,
        }
        parts: list[str] = []
        for resource, delta in deltas.items():
            if abs(delta) <= 1e-9:
                continue
            sign = "+" if delta > 0 else "-"
            parts.append(f"{sign}{abs(delta):g} {resource}")
        if parts:
            return ", ".join(parts)
        if action == "skip":
            return "No effect (skip)"
        return "No effect"


def _select_outcome(offer: OfferSpec, action: str) -> OutcomeSpec:
    if action == "approve":
        return offer.approve
    if action == "reject":
        return offer.reject
    if action == "dismiss":
        return offer.dismiss or offer.reject
    raise ActionNotAllowed(f"Unknown action '{action}'")


def _effect_applies(effect: EffectSpec, state: GameState) -> bool:
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


def _resource_label(resource: object) -> str:
    labels = {
        "coins": "coins",
        "pop": "popularity",
        "mh": "health",
        "dismissals": "dismissals",
        "retirement_chests": "chests",
    }
    return labels.get(str(resource), str(resource))


def _build_random_choices(
    random_spec: BernoulliSpec | CategoricalSpec | None,
    state: GameState,
    data: JusticeData,
) -> list[dict[str, object]]:
    choices: list[dict[str, object]] = []
    if random_spec is None:
        return choices
    if isinstance(random_spec, BernoulliSpec):
        for label, effects, key in (
            ("Then", random_spec.then_effects, "then"),
            ("Else", random_spec.else_effects, "else"),
        ):
            summary = summarize_outcome(OutcomeSpec(effects=effects), state, data)
            choices.append(
                {
                    "display": f"{label}: {summary}",
                    "effects": effects,
                    "label": key,
                }
            )
        return choices
    for idx, choice in enumerate(random_spec.choices, start=1):
        label = choice.label or f"Choice {idx}"
        summary = summarize_outcome(OutcomeSpec(effects=choice.effects), state, data)
        choices.append(
            {
                "display": f"{label}: {summary}",
                "effects": choice.effects,
                "label": choice.label,
            }
        )
    return choices


def _build_extra_effects(
    entry: LogEntry, data: JusticeData
) -> list[tuple[str, tuple[EffectSpec, ...], GameState]]:
    offer = data.offers_by_id.get(entry.offer_id)
    if not offer:
        return []
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
            extras.append((label, pre_state.required_action_penalty_effects, pre_state))

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

        for trigger in _fired_encounter_triggers(pre_state, post_state, offer):
            extras.append(
                (
                    _encounter_trigger_label(trigger, offer, data),
                    trigger.effects,
                    pre_state,
                )
            )

        for trigger in _fired_action_triggers(pre_state, post_state, offer, action):
            extras.append(
                (
                    _action_trigger_label(trigger, offer, data),
                    trigger.effects,
                    pre_state,
                )
            )

        if (
            action == "approve"
            and offer.id == data.special_rules.harbinger.offer_id
            and data.special_rules.harbinger.on_unpaid_effects
        ):
            cost = resolve_expr(
                {"expr": data.special_rules.harbinger.cost_expr}, pre_state, data
            )
            if pre_state.coins < cost:
                extras.append(
                    (
                        "Harbinger unpaid",
                        tuple(data.special_rules.harbinger.on_unpaid_effects),
                        pre_state,
                    )
                )

    next_case = pre_state.case_index + 1
    for event in pre_state.scheduled_events:
        if event.trigger_case_index != next_case:
            continue
        label = "Scheduled effect"
        if event.label:
            label = f"Scheduled: {_humanize_label(event.label)}"
        extras.append((label, event.effects, post_state))

    return extras


def _fired_encounter_triggers(
    pre_state: GameState, post_state: GameState, offer: OfferSpec
) -> list[EncounterTrigger]:
    fired: list[EncounterTrigger] = []
    for trigger in pre_state.encounter_triggers:
        if not _encounter_trigger_matches(trigger, offer):
            continue
        if _trigger_fired(trigger, pre_state, post_state, is_action=False):
            fired.append(trigger)
    return fired


def _fired_action_triggers(
    pre_state: GameState,
    post_state: GameState,
    offer: OfferSpec,
    action: str,
) -> list[ActionTrigger]:
    fired: list[ActionTrigger] = []
    for trigger in pre_state.action_triggers:
        if not _action_trigger_matches(trigger, offer, action):
            continue
        if _trigger_fired(trigger, pre_state, post_state, is_action=True):
            fired.append(trigger)
    return fired


def _trigger_fired(
    trigger: ActionTrigger | EncounterTrigger,
    pre_state: GameState,
    post_state: GameState,
    *,
    is_action: bool,
) -> bool:
    remaining = trigger.remaining_uses
    if remaining is None or remaining < 0:
        return _predicate_allows(trigger.when, pre_state)
    post_remaining = _remaining_uses_after(post_state, trigger, is_action=is_action)
    if post_remaining is None:
        return True
    return post_remaining < remaining


def _remaining_uses_after(
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
            if not _same_action_trigger(candidate, trigger):
                continue
        else:
            if not _same_encounter_trigger(candidate, trigger):
                continue
        return candidate.remaining_uses
    return None


def _same_action_trigger(left: ActionTrigger, right: ActionTrigger) -> bool:
    return (
        left.action == right.action
        and left.npc_id == right.npc_id
        and left.offer_id == right.offer_id
        and left.when == right.when
        and left.label == right.label
        and left.effects == right.effects
    )


def _same_encounter_trigger(left: EncounterTrigger, right: EncounterTrigger) -> bool:
    return (
        left.npc_id == right.npc_id
        and left.offer_id == right.offer_id
        and left.when == right.when
        and left.label == right.label
        and left.effects == right.effects
    )


def _encounter_trigger_matches(trigger: EncounterTrigger, offer: OfferSpec) -> bool:
    if trigger.offer_id and trigger.offer_id != offer.id:
        return False
    if trigger.npc_id and trigger.npc_id != offer.npc_id:
        return False
    return True


def _action_trigger_matches(
    trigger: ActionTrigger, offer: OfferSpec, action: str
) -> bool:
    if trigger.action not in {"any", action}:
        return False
    if trigger.offer_id and trigger.offer_id != offer.id:
        return False
    if trigger.npc_id and trigger.npc_id != offer.npc_id:
        return False
    return True


def _encounter_trigger_label(
    trigger: EncounterTrigger, offer: OfferSpec, data: JusticeData
) -> str:
    if trigger.label:
        return f"Encounter trigger: {_humanize_label(trigger.label)}"
    target = _trigger_target(
        trigger.npc_id, trigger.offer_id, offer, data, fallback="any encounter"
    )
    if target:
        return f"Encounter trigger: {target}"
    return "Encounter trigger"


def _action_trigger_label(
    trigger: ActionTrigger, offer: OfferSpec, data: JusticeData
) -> str:
    if trigger.label:
        return f"Action trigger: {_humanize_label(trigger.label)}"
    action_label = trigger.action if trigger.action != "any" else "any"
    target = _trigger_target(
        trigger.npc_id, trigger.offer_id, offer, data, fallback="any offer"
    )
    if target:
        return f"Action trigger: {action_label} @ {target}"
    return f"Action trigger: {action_label}"


def _trigger_target(
    npc_id: str | None,
    offer_id: str | None,
    offer: OfferSpec,
    data: JusticeData,
    *,
    fallback: str,
) -> str:
    if npc_id:
        npc = data.npcs_by_id.get(npc_id)
        return npc.name if npc else npc_id
    if offer_id:
        target_offer = data.offers_by_id.get(offer_id)
        return target_offer.title if target_offer else offer_id
    return fallback


def _predicate_allows(predicate: str | None, state: GameState) -> bool:
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


def _humanize_label(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in text.split())


def main() -> int:
    console = Console()
    data = load_builtin_data()
    suggested_rules = load_builtin_suggested_rules(data)
    app = CliApp(data, suggested_rules, console=console)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
