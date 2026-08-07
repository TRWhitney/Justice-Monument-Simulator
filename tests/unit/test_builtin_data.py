import pytest

from justice_sim.config import load_builtin_data


def _offer(data, title):
    return next(offer for offer in data.offers if offer.title == title)


def _resource_effects(outcome):
    return [
        (effect.params["resource"], effect.params["amount"])
        for effect in outcome.effects
        if effect.type == "add_resource"
    ]


@pytest.mark.unit
def test_confirmed_builtin_outcomes_match_justice_monument_table():
    data = load_builtin_data()

    life_insurance = _offer(data, "Honcho: Life Insurance")
    assert _resource_effects(life_insurance.approve)[:1] == [("mh", 4)]
    assert ("pop", 2) not in _resource_effects(life_insurance.approve)
    assert _resource_effects(life_insurance.reject) == [("pop", 2)]

    rough_cut = _offer(data, "Mister Bribe: Rough Cut")
    assert _resource_effects(rough_cut.approve)[0] == (
        "coins",
        {"expr": "7", "scaling": "case"},
    )

    jackpot = _offer(data, "Retirement Chester: Jackpot Boost")
    assert _resource_effects(jackpot.approve)[1] == (
        "coins",
        {"expr": "-10", "scaling": "case"},
    )

    double_dip = _offer(data, "Retirement Chester: Double Dip")
    assert _resource_effects(double_dip.approve)[1] == (
        "coins",
        {"expr": "-2", "scaling": "case"},
    )

    kitchen_loan = _offer(data, "Scripticus: Kitchen Loan")
    repayment = next(
        effect
        for effect in kitchen_loan.approve.effects
        if effect.type == "add_encounter_trigger"
    )
    assert repayment.params["effects"][0]["params"]["amount"] == {
        "expr": "2.5",
        "scaling": "case",
        "snapshot": True,
    }

    promise = _offer(data, "Scripticus: Promise Me")
    assert _resource_effects(promise.approve) == [
        ("coins", {"expr": "3", "scaling": "case"})
    ]

    busted_bills = _offer(data, "Harbinger: Busted Bills")
    assert _resource_effects(busted_bills.approve)[0] == (
        "pop",
        {"expr": "-1", "scaling": "case"},
    )


@pytest.mark.unit
def test_confirmed_builtin_durations_and_notes_are_accurate():
    data = load_builtin_data()

    approval_lock = _offer(data, "Mister Bribe: Approval Lock")
    status = next(
        effect
        for effect in approval_lock.approve.effects
        if effect.type == "add_status"
    )
    assert status.duration_cases == 3
    assert not status.params.get("data", {}).get("starts_next_case", False)
    assert "acceptance counts as the first" in approval_lock.notes.lower()

    gratefulbinger = _offer(data, "Gratefulbinger: Thank-You")
    assert "(40*POP)/(POP+20)" in gratefulbinger.notes

    for title in (
        "Harbinger: Rent Due",
        "Harbinger: Stream Crash",
        "Harbinger: Coma Crash",
    ):
        assert "0 Popularity" not in _offer(data, title).notes
