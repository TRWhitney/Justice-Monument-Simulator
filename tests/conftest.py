from __future__ import annotations

from typing import Any

import pytest

from justice_sim.models.offer import JusticeData


def build_data_dict(
    *,
    debt_mode: str = "clamp_to_zero",
    include_grateful: bool = True,
    cost_expr: str = "5",
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "version": "test",
        "defaults": {
            "debt_mode": debt_mode,
            "default_probability_format": "unit",
            "encounter_model_default": "uniform",
            "planner_defaults": {
                "horizon_cases": 5,
                "rollouts_per_action": 25,
                "adaptive_rollouts": False,
                "adaptive_rollouts_max": 50,
                "risk_preset": "balanced",
            },
        },
        "npcs": [
            {"id": "npc1", "name": "NPC One"},
            {"id": "npc2", "name": "NPC Two"},
            {"id": "the_harbinger", "name": "The Harbinger"},
            {"id": "the_gratefulbinger", "name": "The Gratefulbinger"},
            {"id": "little_timmy", "name": "Little Timmy"},
        ],
        "offers": [
            {
                "id": "offer1",
                "npc_id": "npc1",
                "title": "Offer One",
                "text": "Hello world",
                "actions_available": ["approve", "reject", "dismiss"],
                "approve": {
                    "effects": [
                        {
                            "type": "add_resource",
                            "params": {"resource": "coins", "amount": 2},
                        }
                    ]
                },
                "reject": {
                    "effects": [
                        {
                            "type": "add_resource",
                            "params": {"resource": "pop", "amount": -1},
                        }
                    ]
                },
                "dismiss": {"effects": []},
            },
            {
                "id": "offer2",
                "npc_id": "npc2",
                "title": "Offer Two",
                "text": "Another text",
                "actions_available": ["approve", "reject"],
                "approve": {
                    "effects": [
                        {
                            "type": "add_resource",
                            "params": {
                                "resource": "retirement_chests",
                                "amount": 1,
                            },
                        }
                    ]
                },
                "reject": {
                    "effects": [
                        {
                            "type": "add_resource",
                            "params": {
                                "resource": "coins",
                                "amount": {
                                    "expr": "-1",
                                    "scaling": "harbinger",
                                },
                            },
                        }
                    ]
                },
            },
            {
                "id": "harbinger_offer",
                "npc_id": "the_harbinger",
                "allow_insufficient_funds": True,
                "title": "Harbinger",
                "text": "Pay up",
                "actions_available": ["approve", "reject"],
                "approve": {
                    "effects": [
                        {
                            "type": "add_resource",
                            "params": {"resource": "coins", "amount": -1},
                        }
                    ]
                },
                "reject": {
                    "effects": [
                        {
                            "type": "add_resource",
                            "params": {"resource": "mh", "amount": -1},
                        }
                    ]
                },
            },
            {
                "id": "grateful_offer",
                "npc_id": "the_gratefulbinger",
                "title": "Grateful",
                "text": "Thanks",
                "actions_available": ["approve", "reject"],
                "approve": {
                    "effects": [
                        {
                            "type": "add_resource",
                            "params": {"resource": "coins", "amount": 1},
                        }
                    ]
                },
                "reject": {"effects": []},
            },
            {
                "id": "timmy_offer",
                "npc_id": "little_timmy",
                "title": "Timmy",
                "text": "Timmy text",
                "actions_available": ["approve", "reject"],
                "approve": {"effects": []},
                "reject": {"effects": []},
            },
        ],
        "special_rules": {
            "case_scale": {"mode": "expr", "expr": "ceil(case_index/5)"},
            "harbinger": {
                "offer_id": "harbinger_offer",
                "cadence_modulus": 5,
                "cost_expr": cost_expr,
                "on_unpaid_effects": [],
            },
        },
    }
    if include_grateful:
        data["special_rules"]["gratefulbinger"] = {
            "offer_id": "grateful_offer",
            "replace_harbinger_probability_expr": "(40*pop)/(pop+20)",
            "format": "percent",
        }
    return data


@pytest.fixture
def data_dict_factory():
    def _factory(**kwargs: Any) -> dict[str, Any]:
        return build_data_dict(**kwargs)

    return _factory


@pytest.fixture
def data_factory(data_dict_factory):
    def _factory(**kwargs: Any) -> JusticeData:
        return JusticeData.from_dict(data_dict_factory(**kwargs))

    return _factory
