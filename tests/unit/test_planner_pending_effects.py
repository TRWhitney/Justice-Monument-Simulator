from dataclasses import replace

import pytest

from justice_sim.models.offer import EffectSpec, OutcomeSpec
from justice_sim.models.state import (
    EncounterTrigger,
    ForcedEncounter,
    GameState,
    ScheduledEvent,
)
from justice_sim.planner.rollout import PlannerConfig, RolloutPlanner

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("kind", ["scheduled", "arrival"])
def test_resource_condition_in_pending_deal_prevents_unsafe_shortcut(
    data_factory, kind
):
    data = data_factory(include_grateful=False)
    quiet = replace(data.offers[1], approve=OutcomeSpec(), reject=OutcomeSpec())
    data = replace(data, offers_by_id={**data.offers_by_id, quiet.id: quiet})
    effect = EffectSpec("end_run", {}, when="coins > 5")
    state = GameState(
        1, 5, 3, 3, 0, 0, forced_encounters=(ForcedEncounter(2, quiet.id),)
    )
    if kind == "scheduled":
        state = replace(state, scheduled_events=(ScheduledEvent(3, (effect,)),))
    else:
        state = replace(
            state,
            encounter_triggers=(
                EncounterTrigger(effects=(effect,), when="case_index >= 2"),
            ),
        )
    offer = replace(
        data.offers[0], actions_available=("approve", "reject"), reject=OutcomeSpec()
    )
    planner = RolloutPlanner(
        data,
        PlannerConfig(horizon_cases=1, rollouts_per_action=8, adaptive_rollouts=False),
        seed=1,
    )
    progress = []
    result = planner.recommend(state, offer, progress.append)
    assert progress and result.best_action == "reject"
    scores = {s.action: s for s in result.action_scores}
    assert scores["approve"].death_probability == 1
    assert scores["reject"].death_probability == 0


@pytest.mark.parametrize(
    "title,case",
    [
        ("Gratefulbinger: Thank-You", 5),
        ("Concerned Poppy: Fan Mail", 1),
    ],
)
def test_builtin_gifts_keep_shortcuts_with_fixed_pending_payments(
    builtin_data, title, case
):
    offer = next(o for o in builtin_data.offers if o.title == title)
    # Both an ordinary state and a harmless pending commitment retain the shortcut.
    planner = RolloutPlanner.from_defaults(builtin_data, seed=1)
    for events in (
        (),
        (
            ScheduledEvent(
                case + 3,
                (EffectSpec("add_resource", {"resource": "coins", "amount": 5}),),
            ),
        ),
    ):
        state = GameState(case, 10, 5, 3, 1, 0, scheduled_events=events)
        progress = []
        result = planner.recommend(state, offer, progress.append)
        assert result.best_action == "approve"
        assert not progress
        assert all(s.sample_count == 0 for s in result.action_scores)


def test_unrelated_resource_condition_does_not_disable_shortcut(data_factory):
    data = data_factory()
    offer = replace(
        data.offers[0], actions_available=("approve", "reject"), reject=OutcomeSpec()
    )
    state = GameState(
        1,
        5,
        3,
        3,
        0,
        0,
        scheduled_events=(
            ScheduledEvent(3, (EffectSpec("end_run", {}, when="mh <= 1"),)),
        ),
    )
    planner = RolloutPlanner.from_defaults(data, seed=1)
    progress = []
    result = planner.recommend(state, offer, progress.append)
    assert result.best_action == "approve" and not progress
