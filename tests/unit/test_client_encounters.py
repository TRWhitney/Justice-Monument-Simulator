"""Exact conditional encounter probabilities from the official client."""

from dataclasses import replace

import pytest

from justice_sim.engine.encounter import (
    UniformEncounterModel,
    WeightedEncounterModel,
    LearnedEncounterModel,
    client_encounter_probabilities,
    select_encounter,
    possible_encounter_offers,
)
from justice_sim.engine.reducer import apply_action
from justice_sim.engine.rng import Rng
from justice_sim.models.state import GameState, EncounterOverride

pytestmark = pytest.mark.unit


def offer(data, row):
    return next(o for o in data.offers if row in o.client_rows)


def state(**changes):
    return replace(GameState(1, 20, 20, 5, 3, 7), **changes)


def probabilities(data, s=None, model=None):
    return client_encounter_probabilities(
        s or state(), data, model or UniformEncounterModel()
    )


def test_client_rows_are_complete_and_group_weights_are_preserved(builtin_data):
    assert sorted(row for o in builtin_data.offers for row in o.client_rows) == list(
        range(90)
    )
    p = probabilities(builtin_data)
    assert sum(p.values()) == pytest.approx(1)
    assert p[offer(builtin_data, 44).id] == pytest.approx(5 / 71)
    assert p[offer(builtin_data, 70).id] == pytest.approx(2 / 71)
    assert p[offer(builtin_data, 80).id] == pytest.approx(1 / 71)
    assert offer(builtin_data, 72).id not in p
    assert offer(builtin_data, 86).id not in p


def test_post_harbinger_chester_override_includes_ordinary_mass(builtin_data):
    p = probabilities(builtin_data, state(case_index=6))
    assert p[offer(builtin_data, 21).id] == pytest.approx(0.2 + 0.6 / 71)
    assert p[offer(builtin_data, 22).id] == pytest.approx(0.2 + 0.6 / 71)
    assert p[offer(builtin_data, 0).id] == pytest.approx(0.6 / 71)


@pytest.mark.parametrize(
    "changes,row",
    [
        ({"coins": 0}, 14),
        ({"coins": 0, "counters": {"harbinger_broke_stage": 1}}, 15),
        ({"pop": 0}, 12),
        ({"counters": {"timmy_rejects": 3}}, 13),
        ({"coins": 0, "pop": 0, "counters": {"timmy_rejects": 3}}, 14),
        ({"pop": 0, "counters": {"timmy_rejects": 3}}, 13),
    ],
)
def test_harbinger_priority(builtin_data, changes, row):
    p = probabilities(builtin_data, state(case_index=5, **changes))
    grateful = offer(builtin_data, 25).id
    assert set(p) - {grateful} == {offer(builtin_data, row).id}


@pytest.mark.parametrize(
    "pop,probability", [(0, 0), (1, 0), (2, 0), (3, 0.4 * 3 / 23), (20, 0.2)]
)
def test_gratefulbinger_requires_three_popularity(builtin_data, pop, probability):
    assert probabilities(builtin_data, state(case_index=5, pop=pop)).get(
        offer(builtin_data, 25).id, 0
    ) == pytest.approx(probability)


def test_timmy_meltdown_consumes_rejections(builtin_data):
    s = state(case_index=5, counters={"timmy_rejects": 3})
    s, _ = apply_action(s, offer(builtin_data, 13), "reject", builtin_data, Rng(0))
    assert s.counters.get("timmy_rejects", 0) == 0
    assert offer(builtin_data, 13).id not in probabilities(
        builtin_data, replace(s, case_index=10)
    )


def test_magnet_pool_precedes_secret_and_skips_harbinger(builtin_data):
    s = state(
        case_index=5,
        counters={"fizarre_drink_approves": 3},
        encounter_overrides=(
            EncounterOverride(
                npc_id="retirement_chester",
                label="chest_magnetizer",
                remaining_uses=3,
                priority=10,
            ),
        ),
    )
    assert offer(builtin_data, 61).id not in probabilities(builtin_data, s)
    for case in (6, 7, 8):
        s = replace(s, case_index=case)
        p = probabilities(builtin_data, s)
        assert set(p) == {offer(builtin_data, r).id for r in (21, 22, 33, 37, 39, 52)}
        assert all(v == pytest.approx(1 / 6) for v in p.values())
        chosen = select_encounter(s, builtin_data, UniformEncounterModel(), Rng(0))
        s, _ = apply_action(
            s, builtin_data.offers_by_id[chosen], "reject", builtin_data, Rng(0)
        )
    assert probabilities(builtin_data, s) == {offer(builtin_data, 61).id: 1}
    s, _ = apply_action(s, offer(builtin_data, 61), "dismiss", builtin_data, Rng(0))
    assert s.counters.get("fizarre_drink_approves", 0) == 0


def test_bean_loan_bias_targets_other_beans_and_clears_on_payback(builtin_data):
    s, _ = apply_action(
        state(), offer(builtin_data, 26), "approve", builtin_data, Rng(0)
    )
    p = probabilities(builtin_data, s)
    base = UniformEncounterModel().eligible_offers(s, builtin_data)
    total = sum(builtin_data.offers_by_id[k].encounter_weight for k in base)
    assert offer(builtin_data, 26).id not in p
    for row in (27, 28, 29):
        assert p[offer(builtin_data, row).id] == pytest.approx(0.05 + 0.85 / total)
    s, _ = apply_action(s, offer(builtin_data, 28), "reject", builtin_data, Rng(0))
    assert s.coins == 20
    assert not s.encounter_overrides


@pytest.mark.parametrize("row", [29, 36, 43, 53, 55, 63, 75, 85])
def test_active_deals_do_not_reappear(builtin_data, row):
    s, _ = apply_action(
        state(), offer(builtin_data, row), "approve", builtin_data, Rng(0)
    )
    assert offer(builtin_data, row).id not in UniformEncounterModel().eligible_offers(
        s, builtin_data
    )


def test_magic_rupie_requires_and_consumes_three_approvals(builtin_data):
    s = state()
    for count in range(3):
        assert offer(
            builtin_data, 86
        ).id not in UniformEncounterModel().eligible_offers(s, builtin_data)
        s, _ = apply_action(s, offer(builtin_data, 69), "approve", builtin_data, Rng(0))
    assert offer(builtin_data, 86).id in UniformEncounterModel().eligible_offers(
        s, builtin_data
    )
    s, _ = apply_action(s, offer(builtin_data, 86), "approve", builtin_data, Rng(0))
    assert offer(builtin_data, 86).id not in UniformEncounterModel().eligible_offers(
        s, builtin_data
    )


@pytest.mark.parametrize(
    "model",
    [UniformEncounterModel(), WeightedEncounterModel(), LearnedEncounterModel()],
)
def test_sampling_and_possible_offers_share_distribution(builtin_data, model):
    s = state(case_index=6)
    assert set(possible_encounter_offers(s, builtin_data, model)) == set(
        probabilities(builtin_data, s, model)
    )
    assert all(
        select_encounter(s, builtin_data, model, Rng(seed))
        in probabilities(builtin_data, s, model)
        for seed in range(10)
    )


@pytest.mark.parametrize(
    "changes,risk",
    [
        ({"coins": 0, "pop": 0, "counters": {"harbinger_broke_stage": 1}}, 1),
        ({"coins": 0, "pop": 20, "dismissals": 0}, 0),
        (
            {
                "coins": 0,
                "pop": 2,
                "dismissals": 0,
                "counters": {"harbinger_broke_stage": 1},
            },
            1,
        ),
    ],
)
def test_harbinger_risk_uses_actual_payment_and_dismissal(changes, risk, builtin_data):
    from justice_sim.engine.scoring import _next_harbinger_risk

    assert _next_harbinger_risk(
        state(case_index=5, **changes), builtin_data
    ) == pytest.approx(risk)


def test_pending_investment_survives_saved_run_round_trip(builtin_data):
    from justice_sim.persistence.runs import serialize_state, deserialize_state

    s, _ = apply_action(
        state(), offer(builtin_data, 43), "approve", builtin_data, Rng(0)
    )
    restored = deserialize_state(serialize_state(s))
    assert restored == s
    assert offer(builtin_data, 43).id not in UniformEncounterModel().eligible_offers(
        restored, builtin_data
    )
