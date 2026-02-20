import pytest

from justice_sim.engine.reducer import (
    ActionNotAllowed,
    apply_action,
    apply_action_with_outcome,
    can_afford_action,
    skip_case,
)
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import EffectSpec, JusticeData, OutcomeSpec
from justice_sim.models.state import (
    ActionTrigger,
    EncounterTrigger,
    GameState,
    StatusEffect,
)


@pytest.mark.unit
def test_required_action_penalty_applied_when_violated(data_factory):
    data = data_factory()
    offer = data.offers_by_id["offer1"]
    state = GameState(
        case_index=1,
        coins=0,
        pop=1,
        mh=2,
        dismissals=0,
        retirement_chests=0,
        required_action="approve",
        required_action_penalty_effects=(
            EffectSpec(
                type="add_resource",
                params={"resource": "mh", "amount": -1},
            ),
        ),
    )
    rng = Rng(1)
    new_state, _ = apply_action(state, offer, "reject", data, rng)
    assert new_state.mh == 1
    assert new_state.required_action is None


@pytest.mark.unit
def test_insufficient_funds_blocked_in_allow_negative_mode(data_dict_factory):
    data_dict = data_dict_factory(debt_mode="allow_negative")
    data_dict["offers"][0]["approve"]["effects"][0]["params"]["amount"] = -10
    data = JusticeData.from_dict(data_dict)
    offer = data.offers_by_id["offer1"]
    state = GameState(
        case_index=1, coins=0, pop=0, mh=2, dismissals=0, retirement_chests=0
    )
    with pytest.raises(ActionNotAllowed):
        apply_action(state, offer, "approve", data, Rng(2))


@pytest.mark.unit
def test_insufficient_funds_allowed_with_override(data_dict_factory):
    data_dict = data_dict_factory(debt_mode="allow_negative")
    data_dict["offers"][0]["approve"]["effects"][0]["params"]["amount"] = -10
    data_dict["offers"][0]["allow_insufficient_funds"] = True
    data = JusticeData.from_dict(data_dict)
    offer = data.offers_by_id["offer1"]
    state = GameState(
        case_index=1, coins=0, pop=0, mh=2, dismissals=0, retirement_chests=0
    )
    new_state, _ = apply_action(state, offer, "approve", data, Rng(2))
    assert new_state.coins < 0


@pytest.mark.unit
def test_insufficient_funds_blocked_in_clamp_mode(data_dict_factory):
    data_dict = data_dict_factory(debt_mode="clamp_to_zero")
    data_dict["offers"][0]["approve"]["effects"][0]["params"]["amount"] = -10
    data = JusticeData.from_dict(data_dict)
    offer = data.offers_by_id["offer1"]
    state = GameState(
        case_index=1, coins=0, pop=0, mh=2, dismissals=0, retirement_chests=0
    )
    with pytest.raises(ActionNotAllowed):
        apply_action(state, offer, "approve", data, Rng(2))


@pytest.mark.unit
def test_insufficient_funds_clamped_with_override(data_dict_factory):
    data_dict = data_dict_factory(debt_mode="clamp_to_zero")
    data_dict["offers"][0]["approve"]["effects"][0]["params"]["amount"] = -10
    data_dict["offers"][0]["allow_insufficient_funds"] = True
    data = JusticeData.from_dict(data_dict)
    offer = data.offers_by_id["offer1"]
    state = GameState(
        case_index=1, coins=0, pop=0, mh=2, dismissals=0, retirement_chests=0
    )
    new_state, _ = apply_action(state, offer, "approve", data, Rng(2))
    assert new_state.coins == 0


@pytest.mark.unit
def test_reject_allows_popularity_to_clamp_to_zero(data_dict_factory):
    data_dict = data_dict_factory()
    data_dict["offers"][0]["reject"]["effects"][0]["params"]["amount"] = -10
    data = JusticeData.from_dict(data_dict)
    offer = data.offers_by_id["offer1"]
    state = GameState(
        case_index=1, coins=0, pop=3, mh=2, dismissals=0, retirement_chests=0
    )
    assert can_afford_action(state, offer, "reject", data)
    new_state, _ = apply_action(state, offer, "reject", data, Rng(2))
    assert new_state.pop == 0


@pytest.mark.unit
def test_reject_still_blocks_insufficient_coins(data_dict_factory):
    data_dict = data_dict_factory()
    data_dict["offers"][0]["reject"]["effects"][0]["params"]["resource"] = "coins"
    data_dict["offers"][0]["reject"]["effects"][0]["params"]["amount"] = -10
    data = JusticeData.from_dict(data_dict)
    offer = data.offers_by_id["offer1"]
    state = GameState(
        case_index=1, coins=3, pop=0, mh=2, dismissals=0, retirement_chests=0
    )
    assert not can_afford_action(state, offer, "reject", data)


@pytest.mark.unit
def test_dismiss_requires_dismissals(data_factory):
    data = data_factory()
    offer = data.offers_by_id["offer1"]
    state = GameState(
        case_index=1, coins=0, pop=1, mh=2, dismissals=0, retirement_chests=0
    )
    with pytest.raises(ActionNotAllowed):
        apply_action(state, offer, "dismiss", data, Rng(2))


@pytest.mark.unit
def test_dismiss_consumes_dismissal(data_factory):
    data = data_factory()
    offer = data.offers_by_id["offer1"]
    state = GameState(
        case_index=1, coins=0, pop=1, mh=2, dismissals=1, retirement_chests=0
    )
    new_state, _ = apply_action(state, offer, "dismiss", data, Rng(2))
    assert new_state.dismissals == 0


@pytest.mark.unit
def test_skip_advances_case_without_consuming_dismissals(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1, coins=2, pop=1, mh=3, dismissals=2, retirement_chests=0
    )
    new_state = skip_case(state, data, Rng(3))

    assert new_state.case_index == 2
    assert new_state.dismissals == 2
    assert new_state.coins == state.coins
    assert new_state.pop == state.pop
    assert new_state.mh == state.mh


@pytest.mark.unit
def test_dismiss_not_allowed_with_override(data_dict_factory):
    data_dict = data_dict_factory()
    data_dict["offers"][0]["allow_insufficient_funds"] = True
    data = JusticeData.from_dict(data_dict)
    offer = data.offers_by_id["offer1"]
    state = GameState(
        case_index=1, coins=0, pop=1, mh=2, dismissals=0, retirement_chests=0
    )
    with pytest.raises(ActionNotAllowed):
        apply_action(state, offer, "dismiss", data, Rng(2))


@pytest.mark.unit
def test_counter_alias_for_little_prefix(data_factory):
    data = data_factory()
    offer = data.offers_by_id["timmy_offer"]
    state = GameState(
        case_index=1, coins=0, pop=0, mh=2, dismissals=0, retirement_chests=0
    )
    new_state, _ = apply_action(state, offer, "reject", data, Rng(3))
    assert new_state.counters["little_timmy_rejects"] == 1
    assert new_state.counters["timmy_rejects"] == 1


@pytest.mark.unit
def test_harbinger_unpaid_penalty_applies(data_dict_factory):
    data_dict = data_dict_factory(cost_expr="5")
    data_dict["special_rules"]["harbinger"]["on_unpaid_effects"] = [
        {"type": "add_resource", "params": {"resource": "mh", "amount": -1}}
    ]
    data = JusticeData.from_dict(data_dict)
    offer = data.offers_by_id["harbinger_offer"]
    state = GameState(
        case_index=5, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    new_state, _ = apply_action(state, offer, "approve", data, Rng(4))
    assert new_state.mh == 2


@pytest.mark.unit
def test_cannot_dismiss_harbinger_blocks_all_harbinger_offers(data_dict_factory):
    data_dict = data_dict_factory()
    data_dict["offers"].append(
        {
            "id": "harbinger_offer_alt",
            "npc_id": "the_harbinger",
            "title": "Harbinger Alt",
            "text": "Alt",
            "actions_available": ["approve", "reject", "dismiss"],
            "approve": {"effects": []},
            "reject": {"effects": []},
            "dismiss": {"effects": []},
        }
    )
    data_dict["offers"].append(
        {
            "id": "grateful_offer_alt",
            "npc_id": "the_gratefulbinger",
            "title": "Grateful Alt",
            "text": "Alt",
            "actions_available": ["approve", "reject", "dismiss"],
            "approve": {"effects": []},
            "reject": {"effects": []},
            "dismiss": {"effects": []},
        }
    )
    data_dict["special_rules"]["gratefulbinger"]["offer_id"] = "grateful_offer_alt"
    data = JusticeData.from_dict(data_dict)
    state = GameState(
        case_index=5,
        coins=0,
        pop=0,
        mh=3,
        dismissals=1,
        retirement_chests=0,
        statuses={
            "cannot_dismiss_harbinger": StatusEffect(
                name="cannot_dismiss_harbinger",
                remaining_cases=-1,
                data={},
            )
        },
    )
    with pytest.raises(ActionNotAllowed):
        apply_action(
            state, data.offers_by_id["harbinger_offer"], "dismiss", data, Rng(1)
        )
    with pytest.raises(ActionNotAllowed):
        apply_action(
            state, data.offers_by_id["harbinger_offer_alt"], "dismiss", data, Rng(1)
        )
    new_state, _ = apply_action(
        state, data.offers_by_id["grateful_offer_alt"], "dismiss", data, Rng(1)
    )
    assert new_state.dismissals == 0


@pytest.mark.unit
def test_action_trigger_applies_on_approve(data_factory):
    data = data_factory()
    offer = data.offers_by_id["offer1"]
    trigger = ActionTrigger(
        action="approve",
        effects=(
            EffectSpec(type="add_resource", params={"resource": "coins", "amount": 3}),
        ),
        remaining_uses=1,
    )
    state = GameState(
        case_index=1,
        coins=0,
        pop=1,
        mh=2,
        dismissals=0,
        retirement_chests=0,
        action_triggers=(trigger,),
    )
    new_state, _ = apply_action(state, offer, "approve", data, Rng(5))
    assert new_state.coins == 5
    assert not new_state.action_triggers


@pytest.mark.unit
def test_encounter_trigger_applies_before_action(data_factory):
    data = data_factory()
    offer = data.offers_by_id["offer1"]
    trigger = EncounterTrigger(
        npc_id="npc1",
        effects=(
            EffectSpec(type="add_resource", params={"resource": "coins", "amount": 4}),
        ),
        remaining_uses=1,
    )
    state = GameState(
        case_index=1,
        coins=0,
        pop=1,
        mh=2,
        dismissals=0,
        retirement_chests=0,
        encounter_triggers=(trigger,),
    )
    new_state, _ = apply_action(state, offer, "approve", data, Rng(6))
    assert new_state.coins == 6
    assert not new_state.encounter_triggers


@pytest.mark.unit
def test_apply_action_with_outcome_override(data_factory):
    data = data_factory()
    offer = data.offers_by_id["offer1"]
    override = OutcomeSpec(
        effects=(
            EffectSpec(type="add_resource", params={"resource": "coins", "amount": 7}),
        )
    )
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=2,
        dismissals=0,
        retirement_chests=0,
    )
    new_state, label = apply_action_with_outcome(
        state, offer, "approve", override, data, Rng(2), random_label="manual"
    )
    assert new_state.coins == 7
    assert label == "manual"
