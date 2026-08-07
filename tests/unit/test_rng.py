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


@pytest.mark.unit
def test_rng_state_roundtrip_after_randint():
    rng = Rng(12345)
    _ = rng.randint(1, 10)
    state = rng.state()
    expected_next = rng.random()

    restored = Rng.from_state(state)

    assert restored.random() == expected_next
