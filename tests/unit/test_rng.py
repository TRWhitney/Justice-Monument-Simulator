import pickle
import random

import pytest

from justice_sim.engine.rng import Rng


class FixedRollRng(Rng):
    def __init__(self, roll):
        self.roll = roll

    def random(self):
        return self.roll


@pytest.mark.unit
def test_rng_state_roundtrip():
    rng = Rng(1234)
    _ = rng.random()
    _ = rng.random()
    state = rng.state()
    rng_next = rng.random()

    restored = Rng.from_state(state)
    assert restored.random() == rng_next


@pytest.mark.unit
def test_rng_spawn_is_deterministic_for_same_token():
    rng = Rng(99)
    assert rng.spawn(10).random() == rng.spawn(10).random()


@pytest.mark.unit
def test_rng_state_roundtrip_after_randint():
    rng = Rng(12345)
    _ = rng.randint(1, 10)
    state = rng.state()
    expected_next = rng.random()

    restored = Rng.from_state(state)

    assert restored.random() == expected_next


@pytest.mark.unit
def test_weighted_choice_does_not_select_zero_weight_at_zero_roll():
    rng = FixedRollRng(0.0)

    assert rng.weighted_choice([("never", 0.0), ("always", 1.0)]) == "always"


@pytest.mark.unit
def test_lazy_rng_matches_python_and_survives_pickle():
    expected = random.Random(42)
    rng = pickle.loads(pickle.dumps(Rng(42)))
    for _ in range(10):
        assert rng.random() == expected.random()
    restored = pickle.loads(pickle.dumps(rng))
    assert restored.random() == expected.random()
    assert restored.state().draws == 11
