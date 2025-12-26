import pytest

from justice_sim.engine.rng import Rng


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
