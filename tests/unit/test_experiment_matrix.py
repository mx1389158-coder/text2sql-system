import json
from pathlib import Path


def test_canonical_matrix_preserves_history_and_covers_four_roles():
    matrix = json.loads(Path("experiments/canonical_2x2.json").read_text(encoding="utf-8"))

    assert set(matrix["cells"]) == {"E00", "E01", "E10", "E11"}
    assert matrix["cells"]["E10"]["actual_run"] == "E20"
    assert matrix["cells"]["E11"]["actual_run"] == "E21"
    assert matrix["model_max_tokens"] == 192
    assert matrix["max_model_calls_per_sample"] == 5
