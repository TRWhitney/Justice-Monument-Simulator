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
        replace(
            state,
            counters=(
                {"timmy_rejects": 3, "rupie_approves": 3}
                if harbinger
                else {"timmy_icecream_stage": 3, "rupie_magic_progress": 3}
            ),
        ),
        builtin_data,
    )
    assert len(contexts) == 2
    if harbinger:
        assert first != second
    else:
        # Independent per-offer evaluation preserves both membership and order.
        excluded = encounter._harbinger_offer_ids(builtin_data) | {
            builtin_data.special_rules.gratefulbinger.offer_id
        }
        changed = replace(
            state, counters={"timmy_icecream_stage": 3, "rupie_magic_progress": 3}
        )
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


def test_equivalent_decisions_reuse_eligibility_without_sharing_results(
    builtin_data, monkeypatch
):
    # Distinct dataset so an earlier scan cannot warm this measurement.
    data = replace(builtin_data)
    model = encounter.UniformEncounterModel()
    state = GameState(2, 100, 20, 3, 2, 0)
    original = encounter.expr_util.evaluate_predicate
    evaluations = 0

    def counted(*args):
        nonlocal evaluations
        evaluations += 1
        return original(*args)

    monkeypatch.setattr(encounter.expr_util, "evaluate_predicate", counted)
    expected = model.eligible_offers(state, data)
    initial_count = evaluations
    assert initial_count > 0
    equivalent = replace(
        state,
        case_index=4,
        coins=500,
        pop=80,
        mh=8,
        counters={"unreferenced_history": 100, "rupie_magic_progress": 2},
    )
    result = model.eligible_offers(equivalent, data)
    assert result == expected
    result.clear()
    assert model.eligible_offers(equivalent, data) == expected
    assert evaluations == initial_count


def test_uniform_proposal_reuses_normalization_and_returns_independent_maps(
    builtin_data, monkeypatch
):
    data = replace(builtin_data)
    state = GameState(2, 100, 20, 3, 2, 0)
    model = encounter.UniformEncounterModel()
    # Warm static row distributions, which have their own normalization.
    model.eligible_offers(state, data)
    original = encounter._normalize_weights
    normalizations = 0

    def counted(weights):
        nonlocal normalizations
        normalizations += 1
        return original(weights)

    monkeypatch.setattr(encounter, "_normalize_weights", counted)
    expected = encounter.client_encounter_probabilities(state, data, model)
    initial_count = normalizations
    assert initial_count > 0
    result = encounter.client_encounter_probabilities(state, data, model)
    assert list(result.items()) == list(expected.items())
    result.clear()
    assert encounter.client_encounter_probabilities(state, data, model) == expected
    assert normalizations == initial_count


def test_custom_predicate_inputs_match_uncached_scans(data_factory):
    from justice_sim.models.state import ScheduledEvent, StatusEffect

    data = data_factory()
    predicates = (
        "mh <= 1",
        "pop + coins >= counters.limit",
        "0 < coins < 20",
        "case_index % 3 == 0",
        "counters.stage >= 3",
        "counters.level + 1 > pop",
        "flags.ready and not statuses.blocked",
        "has_pending('bill')",
        "coins < pop",
        "3 <= counters.stage",
        "has_flag(case_index)",
    )
    offers = tuple(
        replace(data.offers[0], id=f"condition_{i}", conditions=(predicate,))
        for i, predicate in enumerate(predicates)
    )
    data = replace(
        data,
        offers=data.offers + offers,
        offers_by_id=data.offers_by_id | {o.id: o for o in offers},
    )
    model = encounter.UniformEncounterModel()
    index = encounter._encounter_index(data)
    for step in range(300):
        state = GameState(
            step % 9 + 1,
            step % 23,
            step % 13,
            (step % 5) / 2,
            2,
            0,
            counters={"stage": step % 7, "level": step % 5, "limit": step % 31},
            flags=frozenset({"ready"}) if step % 2 else frozenset(),
            statuses={"blocked": StatusEffect("blocked", 2)} if step % 3 else {},
            scheduled_events=(ScheduledEvent(500, (), label="bill"),)
            if step % 4
            else (),
        )
        expected = [
            o.id for o in index.regular if encounter._offer_conditions_allow(o, state)
        ]
        assert model.eligible_offers(state, data) == expected
    assert len(index.eligibility) <= 256


def test_builtin_eligibility_keeps_flags_statuses_and_pending_labels_live(builtin_data):
    from justice_sim.models.state import ScheduledEvent, StatusEffect

    model = encounter.UniformEncounterModel()
    state = GameState(2, 100, 20, 3, 2, 0)
    states = (
        state,
        replace(state, mh=1),
        replace(state, mh=1.001),
        replace(state, counters={"timmy_icecream_stage": 1, "rupie_magic_progress": 3}),
        replace(state, flags=frozenset({"reanimated_hand_share"})),
        replace(state, statuses={"ghost_scare": StatusEffect("ghost_scare", 5)}),
        replace(state, scheduled_events=(ScheduledEvent(100, (), label="poppy_iou"),)),
    )
    index = encounter._encounter_index(builtin_data)
    for changed in (*states, *reversed(states)):
        expected = [
            o.id for o in index.regular if encounter._offer_conditions_allow(o, changed)
        ]
        assert model.eligible_offers(changed, builtin_data) == expected


def test_uniform_extension_dispatch_and_rng_are_preserved(builtin_data):
    from justice_sim.engine.rng import Rng

    model = encounter.UniformEncounterModel()
    state = GameState(2, 100, 20, 3, 2, 0)
    expected = encounter.client_encounter_probabilities(state, builtin_data, model)
    chosen = next(iter(expected))

    class CustomUniform(encounter.UniformEncounterModel):
        def eligible_offers(self, state, data):
            return [chosen]

    assert encounter.client_encounter_probabilities(
        state, builtin_data, CustomUniform()
    ) == {chosen: 1}
    # Instance-level extensions also continue to run on a warm proposal cache.
    model.eligible_offers = lambda state, data: [chosen]
    assert encounter.client_encounter_probabilities(state, builtin_data, model) == {
        chosen: 1
    }
    for seed in range(20):
        actual_rng, reference_rng = Rng(seed), Rng(seed)
        actual = encounter.select_encounter(
            state, builtin_data, encounter.UniformEncounterModel(), actual_rng
        )
        reference = reference_rng.weighted_choice(list(expected.items()))
        assert (actual, actual_rng.state()) == (reference, reference_rng.state())


def test_unreachable_invalid_conditions_keep_lazy_errors(data_factory):
    from justice_sim.util.expr import ExprError

    data = data_factory()
    offer = replace(data.offers[0], conditions=("coins > 0", "malformed +"))
    offers = (offer, *data.offers[1:])
    data = replace(data, offers=offers, offers_by_id={o.id: o for o in offers})
    model = encounter.UniformEncounterModel()
    state = GameState(2, 0, 20, 3, 2, 0)
    assert offer.id not in model.eligible_offers(state, data)
    with pytest.raises(ExprError):
        model.eligible_offers(replace(state, coins=1), data)


def test_arithmetic_resources_keep_integer_and_float_semantics(data_factory):
    data = data_factory()
    offer = replace(data.offers[0], conditions=("coins + 1 > coins",))
    offers = (offer, *data.offers[1:])
    data = replace(data, offers=offers, offers_by_id={o.id: o for o in offers})
    model = encounter.UniformEncounterModel()
    state = GameState(2, 2**53, 20, 3, 2, 0)
    assert offer.id in model.eligible_offers(state, data)
    assert offer.id not in model.eligible_offers(
        replace(state, coins=float(2**53)), data
    )
