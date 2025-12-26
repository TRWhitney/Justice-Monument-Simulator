import pytest

from justice_sim.engine.reducer import ActionNotAllowed, apply_action
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import EffectSpec, JusticeData
from justice_sim.models.state import GameState


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
def test_insufficient_pop_blocked(data_factory):
    data = data_factory()
    offer = data.offers_by_id["offer1"]
    state = GameState(
        case_index=1, coins=0, pop=0, mh=2, dismissals=0, retirement_chests=0
    )
    with pytest.raises(ActionNotAllowed):
        apply_action(state, offer, "reject", data, Rng(2))


@pytest.mark.unit
def test_insufficient_pop_clamped_with_override(data_dict_factory):
    data_dict = data_dict_factory()
    data_dict["offers"][0]["allow_insufficient_funds"] = True
    data = JusticeData.from_dict(data_dict)
    offer = data.offers_by_id["offer1"]
    state = GameState(
        case_index=1, coins=0, pop=0, mh=2, dismissals=0, retirement_chests=0
    )
    new_state, _ = apply_action(state, offer, "reject", data, Rng(2))
    assert new_state.pop == 0


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
