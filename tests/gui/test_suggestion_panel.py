import os

import pytest

from justice_sim.planner.rollout import ActionScore, PlannerRecommendation
from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.widgets.suggestion_panel import SuggestionPanel


@pytest.mark.gui
def test_suggestion_panel_displays_utility_confidence_interval():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    panel = SuggestionPanel()
    recommendation = PlannerRecommendation(
        best_action="approve",
        action_scores=(
            ActionScore(
                action="approve",
                expected_utility=12.0,
                expected_chests=1.0,
                death_probability=0.1,
                variance=4.0,
                sample_count=25,
            ),
        ),
    )

    panel.update_recommendation(recommendation)

    assert "Utility 12.00 ± 0.78 (95% CI)" in panel.metrics_label.text()
    panel.close()
    app.quit()


@pytest.mark.gui
def test_suggestion_panel_displays_no_available_action():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    panel = SuggestionPanel()

    panel.update_recommendation(
        PlannerRecommendation(best_action=None, action_scores=())
    )

    assert panel.best_label.text() == "No available action"
    assert panel.metrics_label.text() == ""
    assert panel.last_action is None
    panel.close()
    app.quit()
