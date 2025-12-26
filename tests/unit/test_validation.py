import pytest

from justice_sim.util.validation import validate_data


@pytest.mark.unit
def test_validation_reports_unknown_effect_type():
    data = {
        "version": "test",
        "npcs": [{"id": "npc", "name": "NPC"}],
        "offers": [
            {
                "id": "offer",
                "npc_id": "npc",
                "title": "Offer",
                "text": "Text",
                "actions_available": ["approve"],
                "approve": {"effects": [{"type": "mystery_effect", "params": {}}]},
                "reject": {"effects": []},
            }
        ],
        "special_rules": {
            "case_scale": {"mode": "expr", "expr": "ceil(case_index/5)"},
            "harbinger": {
                "offer_id": "offer",
                "cadence_modulus": 5,
                "cost_expr": "1",
                "on_unpaid_effects": [],
            },
        },
    }
    errors = validate_data(data)
    assert any("unknown effect type" in error for error in errors)


@pytest.mark.unit
def test_validation_reports_missing_npc_id():
    data = {
        "version": "test",
        "npcs": [{"id": "npc", "name": "NPC"}],
        "offers": [
            {
                "id": "offer",
                "npc_id": "missing",
                "title": "Offer",
                "text": "Text",
                "actions_available": ["approve"],
                "approve": {"effects": []},
                "reject": {"effects": []},
            }
        ],
        "special_rules": {
            "case_scale": {"mode": "expr", "expr": "ceil(case_index/5)"},
            "harbinger": {
                "offer_id": "offer",
                "cadence_modulus": 5,
                "cost_expr": "1",
                "on_unpaid_effects": [],
            },
        },
    }
    errors = validate_data(data)
    assert any("unknown npc_id" in error for error in errors)


@pytest.mark.unit
def test_validation_reports_malformed_predicate():
    data = {
        "version": "test",
        "npcs": [{"id": "npc", "name": "NPC"}],
        "offers": [
            {
                "id": "offer",
                "npc_id": "npc",
                "title": "Offer",
                "text": "Text",
                "actions_available": ["approve"],
                "conditions": ["coins === 1"],
                "approve": {"effects": []},
                "reject": {"effects": []},
            }
        ],
        "special_rules": {
            "case_scale": {"mode": "expr", "expr": "ceil(case_index/5)"},
            "harbinger": {
                "offer_id": "offer",
                "cadence_modulus": 5,
                "cost_expr": "1",
                "on_unpaid_effects": [],
            },
        },
    }
    errors = validate_data(data)
    assert any("malformed predicate" in error for error in errors)


@pytest.mark.unit
def test_validation_reports_duplicate_ids():
    data = {
        "version": "test",
        "npcs": [
            {"id": "npc", "name": "NPC"},
            {"id": "npc", "name": "NPC Duplicate"},
        ],
        "offers": [
            {
                "id": "offer",
                "npc_id": "npc",
                "title": "Offer",
                "text": "Text",
                "actions_available": ["approve"],
                "approve": {"effects": []},
                "reject": {"effects": []},
            },
            {
                "id": "offer",
                "npc_id": "npc",
                "title": "Offer Duplicate",
                "text": "Text",
                "actions_available": ["approve"],
                "approve": {"effects": []},
                "reject": {"effects": []},
            },
        ],
        "special_rules": {
            "case_scale": {"mode": "expr", "expr": "ceil(case_index/5)"},
            "harbinger": {
                "offer_id": "offer",
                "cadence_modulus": 5,
                "cost_expr": "1",
                "on_unpaid_effects": [],
            },
        },
    }
    errors = validate_data(data)
    assert any("duplicate npc id" in error for error in errors)
    assert any("duplicate offer id" in error for error in errors)
