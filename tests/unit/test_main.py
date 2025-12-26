import pytest

from justice_sim import main as main_module


@pytest.mark.unit
def test_main_smoke_flag_returns_zero():
    assert main_module.main(["--smoke"]) == 0


@pytest.mark.unit
def test_main_default_returns_error_code():
    assert main_module.main([]) == 2
