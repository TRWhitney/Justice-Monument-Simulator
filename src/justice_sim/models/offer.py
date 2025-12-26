"""Data models for NPCs, offers, outcomes, and special rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class NpcSpec:
    id: str
    name: str
    image: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class EffectSpec:
    type: str
    params: Mapping[str, Any]
    when: str | Mapping[str, Any] | None = None
    duration_cases: int | None = None
    schedule_after_cases: int | None = None
    label: str | None = None


@dataclass(frozen=True)
class RandomChoiceSpec:
    weight: float
    effects: tuple[EffectSpec, ...]
    label: str | None = None


@dataclass(frozen=True)
class BernoulliSpec:
    type: str
    p: Any
    then_effects: tuple[EffectSpec, ...]
    else_effects: tuple[EffectSpec, ...]


@dataclass(frozen=True)
class CategoricalSpec:
    type: str
    choices: tuple[RandomChoiceSpec, ...]


@dataclass(frozen=True)
class OutcomeSpec:
    effects: tuple[EffectSpec, ...] = ()
    random: BernoulliSpec | CategoricalSpec | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ChainStep:
    trigger: str
    after_cases: int
    offer_id: str
    probability: Any | None = None
    once: bool = True
    notes: str | None = None


@dataclass(frozen=True)
class ChainSpec:
    steps: tuple[ChainStep, ...] = ()


@dataclass(frozen=True)
class OfferSpec:
    id: str
    npc_id: str
    title: str
    text: str
    actions_available: tuple[str, ...]
    approve: OutcomeSpec
    reject: OutcomeSpec
    dismiss: OutcomeSpec | None = None
    tags: tuple[str, ...] = ()
    allow_insufficient_funds: bool | None = None
    conditions: tuple[Any, ...] = ()
    chain: ChainSpec | None = None
    notes: str | None = None


@dataclass(frozen=True)
class CaseScaleRule:
    mode: str
    expr: str


@dataclass(frozen=True)
class HarbingerRule:
    offer_id: str
    cadence_modulus: int
    cost_expr: str
    on_unpaid_effects: tuple[EffectSpec, ...] = ()


@dataclass(frozen=True)
class GratefulbingerRule:
    offer_id: str
    replace_harbinger_probability_expr: str
    format: str = "percent"


@dataclass(frozen=True)
class SpecialRules:
    case_scale: CaseScaleRule
    harbinger: HarbingerRule
    gratefulbinger: GratefulbingerRule | None = None


@dataclass(frozen=True)
class PlannerDefaults:
    horizon_cases: int = 20
    rollouts_per_action: int = 5000
    adaptive_rollouts: bool = True
    adaptive_rollouts_max: int = 20000
    risk_preset: str = "balanced"


@dataclass(frozen=True)
class DefaultsSpec:
    debt_mode: str = "clamp_to_zero"
    default_probability_format: str = "unit"
    encounter_model_default: str = "uniform"
    planner_defaults: PlannerDefaults = field(default_factory=PlannerDefaults)


@dataclass(frozen=True)
class AssetsSpec:
    npc_image_base_path: str | None = None


@dataclass(frozen=True)
class JusticeData:
    version: str
    npcs: tuple[NpcSpec, ...]
    offers: tuple[OfferSpec, ...]
    special_rules: SpecialRules
    defaults: DefaultsSpec = field(default_factory=DefaultsSpec)
    assets: AssetsSpec = field(default_factory=AssetsSpec)
    metadata: Mapping[str, Any] | None = None
    npcs_by_id: Mapping[str, NpcSpec] = field(default_factory=dict)
    offers_by_id: Mapping[str, OfferSpec] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "JusticeData":
        npcs = tuple(_parse_npc(item) for item in data.get("npcs", []))
        offers = tuple(_parse_offer(item) for item in data.get("offers", []))
        defaults = _parse_defaults(data.get("defaults", {}))
        assets = _parse_assets(data.get("assets", {}))
        special_rules = _parse_special_rules(data.get("special_rules", {}))
        npcs_by_id = {npc.id: npc for npc in npcs}
        offers_by_id = {offer.id: offer for offer in offers}
        return JusticeData(
            version=str(data.get("version", "")),
            npcs=npcs,
            offers=offers,
            special_rules=special_rules,
            defaults=defaults,
            assets=assets,
            metadata=data.get("metadata"),
            npcs_by_id=npcs_by_id,
            offers_by_id=offers_by_id,
        )


def _parse_npc(item: Mapping[str, Any]) -> NpcSpec:
    return NpcSpec(
        id=str(item.get("id")),
        name=str(item.get("name")),
        image=item.get("image"),
        tags=tuple(item.get("tags", []) or ()),
    )


def _parse_effect(effect: Mapping[str, Any]) -> EffectSpec:
    return EffectSpec(
        type=str(effect.get("type")),
        params=dict(effect.get("params", {})),
        when=effect.get("when"),
        duration_cases=effect.get("duration_cases"),
        schedule_after_cases=effect.get("schedule_after_cases"),
        label=effect.get("label"),
    )


def _parse_random(random_spec: Mapping[str, Any]) -> BernoulliSpec | CategoricalSpec:
    if random_spec.get("type") == "bernoulli":
        return BernoulliSpec(
            type="bernoulli",
            p=random_spec.get("p"),
            then_effects=tuple(_parse_effect(e) for e in random_spec.get("then", [])),
            else_effects=tuple(_parse_effect(e) for e in random_spec.get("else", [])),
        )
    if random_spec.get("type") == "categorical":
        choices = []
        for choice in random_spec.get("choices", []):
            choices.append(
                RandomChoiceSpec(
                    weight=float(choice.get("weight")),
                    effects=tuple(_parse_effect(e) for e in choice.get("effects", [])),
                    label=choice.get("label"),
                )
            )
        return CategoricalSpec(type="categorical", choices=tuple(choices))
    raise ValueError("Unknown random spec type")


def _parse_outcome(outcome: Mapping[str, Any]) -> OutcomeSpec:
    random_spec = None
    if "random" in outcome and outcome["random"] is not None:
        random_spec = _parse_random(outcome["random"])
    return OutcomeSpec(
        effects=tuple(_parse_effect(e) for e in outcome.get("effects", [])),
        random=random_spec,
        notes=outcome.get("notes"),
    )


def _parse_chain(chain: Mapping[str, Any]) -> ChainSpec:
    steps = []
    for step in chain.get("steps", []):
        steps.append(
            ChainStep(
                trigger=str(step.get("trigger")),
                after_cases=int(step.get("after_cases", 0)),
                offer_id=str(step.get("offer_id")),
                probability=step.get("probability"),
                once=bool(step.get("once", True)),
                notes=step.get("notes"),
            )
        )
    return ChainSpec(steps=tuple(steps))


def _parse_offer(item: Mapping[str, Any]) -> OfferSpec:
    return OfferSpec(
        id=str(item.get("id")),
        npc_id=str(item.get("npc_id")),
        title=str(item.get("title")),
        text=str(item.get("text")),
        actions_available=tuple(item.get("actions_available", []) or ()),
        approve=_parse_outcome(item.get("approve", {})),
        reject=_parse_outcome(item.get("reject", {})),
        dismiss=_parse_outcome(item.get("dismiss", {}))
        if item.get("dismiss")
        else None,
        tags=tuple(item.get("tags", []) or ()),
        allow_insufficient_funds=item.get("allow_insufficient_funds"),
        conditions=tuple(item.get("conditions", []) or ()),
        chain=_parse_chain(item.get("chain", {})) if item.get("chain") else None,
        notes=item.get("notes"),
    )


def _parse_special_rules(data: Mapping[str, Any]) -> SpecialRules:
    case_scale_data = data.get("case_scale", {})
    harbinger_data = data.get("harbinger", {})
    grateful_data = data.get("gratefulbinger")

    case_scale = CaseScaleRule(
        mode=str(case_scale_data.get("mode")),
        expr=str(case_scale_data.get("expr")),
    )
    harbinger = HarbingerRule(
        offer_id=str(harbinger_data.get("offer_id")),
        cadence_modulus=int(harbinger_data.get("cadence_modulus", 5)),
        cost_expr=str(harbinger_data.get("cost_expr")),
        on_unpaid_effects=tuple(
            _parse_effect(e) for e in harbinger_data.get("on_unpaid_effects", [])
        ),
    )
    grateful = None
    if grateful_data:
        grateful = GratefulbingerRule(
            offer_id=str(grateful_data.get("offer_id")),
            replace_harbinger_probability_expr=str(
                grateful_data.get("replace_harbinger_probability_expr")
            ),
            format=str(grateful_data.get("format", "percent")),
        )
    return SpecialRules(
        case_scale=case_scale, harbinger=harbinger, gratefulbinger=grateful
    )


def _parse_defaults(data: Mapping[str, Any]) -> DefaultsSpec:
    planner_raw = data.get("planner_defaults", {})
    planner = PlannerDefaults(
        horizon_cases=int(planner_raw.get("horizon_cases", 20)),
        rollouts_per_action=int(planner_raw.get("rollouts_per_action", 5000)),
        adaptive_rollouts=bool(planner_raw.get("adaptive_rollouts", True)),
        adaptive_rollouts_max=int(planner_raw.get("adaptive_rollouts_max", 20000)),
        risk_preset=str(planner_raw.get("risk_preset", "balanced")),
    )
    return DefaultsSpec(
        debt_mode=str(data.get("debt_mode", "clamp_to_zero")),
        default_probability_format=str(data.get("default_probability_format", "unit")),
        encounter_model_default=str(data.get("encounter_model_default", "uniform")),
        planner_defaults=planner,
    )


def _parse_assets(data: Mapping[str, Any]) -> AssetsSpec:
    return AssetsSpec(npc_image_base_path=data.get("npc_image_base_path"))


def iter_outcome_effects(outcomes: Iterable[OutcomeSpec]) -> Iterable[EffectSpec]:
    for outcome in outcomes:
        for effect in outcome.effects:
            yield effect
        if outcome.random:
            if isinstance(outcome.random, BernoulliSpec):
                for effect in outcome.random.then_effects:
                    yield effect
                for effect in outcome.random.else_effects:
                    yield effect
            elif isinstance(outcome.random, CategoricalSpec):
                for choice in outcome.random.choices:
                    for effect in choice.effects:
                        yield effect
