"""Client rule metadata is optional for existing/custom case datasets."""

import pytest

from justice_sim.models.offer import JusticeData

pytestmark = pytest.mark.unit


def test_legacy_data_keeps_original_rule_defaults(data_factory):
    data = data_factory()
    assert not data.special_rules.client_encounters
    assert not data.special_rules.normalize_after_action
    assert data.special_rules.gratefulbinger.minimum_pop == 0
    assert data.special_rules.harbinger.priority_offers == ()
    for offer in data.offers:
        assert offer.client_rows == ()
        assert offer.encounter_weight == 1
        assert offer.payment_resource is None
        assert not offer.approval_triggers_first
        assert offer.arrival_effects == ()


def test_client_rule_fields_are_parsed(data_dict_factory):
    raw = data_dict_factory()
    raw["offers"][0].update(
        client_rows=[44, 45],
        encounter_weight=2,
        payment_resource="coins",
        approval_triggers_first=True,
        arrival_effects=[{"type": "clear_counter", "params": {"counter": "test"}}],
    )
    raw["special_rules"]["client_encounters"] = True
    raw["special_rules"]["normalize_after_action"] = True
    raw["special_rules"]["gratefulbinger"]["minimum_pop"] = 3
    raw["special_rules"]["harbinger"]["priority_offers"] = ["harbinger_offer"]
    data = JusticeData.from_dict(raw)
    assert data.special_rules.client_encounters
    assert data.special_rules.normalize_after_action
    assert data.special_rules.gratefulbinger.minimum_pop == 3
    assert data.special_rules.harbinger.priority_offers == ("harbinger_offer",)
    offer = data.offers[0]
    assert (offer.client_rows, offer.encounter_weight, offer.payment_resource) == (
        (44, 45),
        2,
        "coins",
    )
    assert offer.approval_triggers_first
    assert offer.arrival_effects[0].params["counter"] == "test"
