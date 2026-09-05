"""Static encounter indexes must preserve ordering and live eligibility inputs."""

from dataclasses import replace

import pytest

from justice_sim.engine import encounter
from justice_sim.models.state import EncounterOverride, GameState

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("harbinger", [False, True])
def test_scan_builds_one_context_and_rechecks_changed_state(
    builtin_data, monkeypatch, harbinger
):
    original = encounter.expr_util.build_predicate_context
    contexts = []

    def counted(**kwargs):
        contexts.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(encounter.expr_util, "build_predicate_context", counted)
    state = GameState(15 if harbinger else 1, 100, 20, 3, 2, 0)
    model = encounter.UniformEncounterModel()
    scan = encounter.eligible_harbinger_offers if harbinger else model.eligible_offers
    first = scan(state, builtin_data)
    assert len(contexts) == 1
    second = scan(
        replace(state, counters={"timmy_rejects": 3, "rupie_approves": 3}), builtin_data
    )
    assert len(contexts) == 2
    if harbinger:
        assert first != second
    else:
        # Independent per-offer evaluation preserves both membership and order.
        excluded = encounter._harbinger_offer_ids(builtin_data) | {
            builtin_data.special_rules.gratefulbinger.offer_id
        }
        changed = replace(state, counters={"timmy_rejects": 3, "rupie_approves": 3})
        assert second == [
            o.id
            for o in builtin_data.offers
            if o.id not in excluded
            and o.encounter_weight > 0
            and encounter._offer_conditions_allow(o, changed)
        ]


def test_static_rows_keep_multiplicity_order_and_return_independent_maps(builtin_data):
    for rows in ((21, 22), (21, 22, 33, 37, 39, 52), (61,), (44, 45, 46, 47, 48)):
        weights = {
            o.id: len(set(o.client_rows).intersection(rows))
            for o in builtin_data.offers
        }
        weights = {k: v for k, v in weights.items() if v}
        expected = {k: v / sum(weights.values()) for k, v in weights.items()}
        first = encounter._client_row_offers(builtin_data, rows)
        assert list(first.items()) == list(expected.items())
        first.clear()
        assert encounter._client_row_offers(builtin_data, rows) == expected


@pytest.mark.parametrize(
    "model_type", [encounter.WeightedEncounterModel, encounter.LearnedEncounterModel]
)
def test_indexes_do_not_freeze_model_weights(builtin_data, model_type):
    model = model_type()
    state = GameState(1, 100, 20, 3, 2, 0)
    first = encounter.client_encounter_probabilities(state, builtin_data, model)
    key = next(iter(first))
    if isinstance(model, encounter.WeightedEncounterModel):
        model.offer_weights = {key: 100}
    else:
        model.counts = {key: 100}
    second = encounter.client_encounter_probabilities(state, builtin_data, model)
    assert second[key] > first[key]
    assert list(first) == list(second)


def test_replaced_datasets_get_their_own_bounded_indexes(builtin_data):
    model = encounter.UniformEncounterModel()
    state = GameState(1, 100, 20, 3, 2, 0)
    first = model.eligible_offers(state, builtin_data)
    for _ in range(10):
        offers = tuple(
            replace(o, encounter_weight=0) if o.id == first[0] else o
            for o in builtin_data.offers
        )
        data = replace(
            builtin_data, offers=offers, offers_by_id={o.id: o for o in offers}
        )
        assert model.eligible_offers(state, data) == first[1:]
    assert len(encounter._ENCOUNTER_INDEXES) <= 8
    assert model.eligible_offers(state, builtin_data) == first


@pytest.mark.parametrize("target", ["offer", "npc", "missing", "empty"])
def test_custom_override_targets_keep_order_and_conditions(builtin_data, target):
    state = GameState(1, 100, 20, 3, 2, 0)
    ordinary = encounter.UniformEncounterModel().eligible_offers(state, builtin_data)
    chosen = builtin_data.offers_by_id[ordinary[0]]
    override = {
        "offer": EncounterOverride(offer_id=chosen.id),
        "npc": EncounterOverride(npc_id=chosen.npc_id),
        "missing": EncounterOverride(offer_id="missing"),
        "empty": EncounterOverride(),
    }[target]
    if target == "offer":
        expected = [chosen.id]
    elif target == "npc":
        expected = [
            o.id
            for o in builtin_data.offers
            if o.npc_id == chosen.npc_id
            and encounter._is_offer_eligible(o, state, builtin_data)
        ]
    else:
        expected = []
    assert (
        encounter._override_candidate_offer_ids(override, state, builtin_data)
        == expected
    )
