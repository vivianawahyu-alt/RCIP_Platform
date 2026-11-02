"""Gate G4: evaluasi AI berskor dengan ambang (TRD §13.5). Bagian copilot diuji di test_synthetic_data."""
from app.ai.evaluate import eval_changes, eval_extraction, eval_grounding_guardrail


def test_change_detection_recall_meets_sm04():
    r = eval_changes()
    assert r["recall"] >= 0.95 and r["spurious"] == 0


def test_grounding_guardrail_catches_all_injected_hallucinations():
    assert eval_grounding_guardrail()["catch_rate"] == 1.0


def test_extractor_v2_not_worse_than_v1_and_baseline_held():
    cur, v1 = eval_extraction(), eval_extraction("v1")
    assert cur["standard"]["schema_invalid"] == 0 and cur["standard"]["grounding_failed"] == 0
    assert cur["heldout"]["accuracy"] >= v1["heldout"]["accuracy"]
    assert cur["heldout"]["accuracy"] >= 0.8, "regresi pada set held-out"
    assert cur["standard"]["f1"] >= 0.9
