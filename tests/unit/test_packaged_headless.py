"""Consumer checks with the source checkout excluded from Python's import path."""

import os
import shutil
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

pytestmark = pytest.mark.unit


def test_encounter_analyzer_remains_available():
    repo = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, str(repo / "scripts/analyze_encounter_runs.py"), "--help"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def test_public_headless_interface():
    from justice_sim.headless import (
        load_builtin_data,
        load_builtin_suggested_rules,
        GameState,
        RolloutPlanner,
    )

    data = load_builtin_data()
    rules = load_builtin_suggested_rules(data)
    planner = RolloutPlanner.from_defaults(data, rules, seed=42)
    offer = next(o for o in data.offers if o.npc_id == "the_gratefulbinger")
    assert (
        planner.recommend(GameState(5, 100, 20, 8, 2, 0), offer).best_action
        == "approve"
    )


def test_installed_wheel_loads_and_plans_without_qt(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    source = tmp_path / "source"
    source.mkdir()
    for name in ("pyproject.toml", "README.md", "UNLICENSE"):
        shutil.copy2(repo / name, source / name)
    shutil.copytree(
        repo / "src",
        source / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
    wheel_dir = tmp_path / "wheels"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(wheel_dir)],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(wheel_dir.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "justice_sim/data/builtin/justice_data.json" in names
        assert "justice_sim/data/schema/justice_data.schema.json" in names
    installed = tmp_path / "venv"
    subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(installed)],
        check=True,
        capture_output=True,
        text=True,
    )
    python = installed / "bin" / "python"
    requirements = tmp_path / "requirements.txt"
    subprocess.run(
        [
            "uv",
            "export",
            "--locked",
            "--no-emit-project",
            "--no-hashes",
            "--output-file",
            str(requirements),
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--no-deps",
            "--requirements",
            str(requirements),
            str(wheel),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    code = """
import sys
from importlib.abc import MetaPathFinder
from pathlib import Path
class BlockQt(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('PySide6', 'justice_sim.ui_qt')):
            raise AssertionError('Qt imported by headless API: ' + fullname)
sys.meta_path.insert(0, BlockQt())
assert not any(Path(p).is_relative_to(Path(sys.argv[2])) for p in sys.path if p)
from justice_sim.headless import load_builtin_data, load_builtin_suggested_rules, RolloutPlanner, GameState
import justice_sim
assert Path(justice_sim.__file__).is_relative_to(Path(sys.argv[1]))
from importlib.metadata import distribution
entrypoints = {entry.name: entry.value for entry in distribution("justicemonumentsimulator").entry_points}
assert entrypoints["justice-sim"] == "justice_sim.ui_cli.cli:main"
assert entrypoints["justice-sim-gui"] == "justice_sim.ui_qt.app:main"
data = load_builtin_data()
rules = load_builtin_suggested_rules(data)
planner = RolloutPlanner.from_defaults(data, rules, seed=42)
offer = next(o for o in data.offers if o.npc_id == 'the_gratefulbinger')
result = planner.recommend(GameState(5, 100, 20, 8, 2, 0), offer, arrival_processed=True)
assert result.best_action == 'approve'
assert not any(name.startswith('PySide6') for name in sys.modules)
"""
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    subprocess.run(
        [str(python), "-I", "-c", code, str(installed), str(repo)],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
