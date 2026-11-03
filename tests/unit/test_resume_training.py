from pathlib import Path

import pytest

from training.scripts.resume_training import latest_checkpoint, validate_checkpoint


def _checkpoint(root: Path, step: int, complete: bool = True) -> Path:
    path = root / f"checkpoint-{step}"
    path.mkdir()
    for name in ("trainer_state.json", "optimizer.pt", "scheduler.pt"):
        if complete or name != "optimizer.pt":
            (path / name).write_text("test", encoding="utf-8")
    return path


def test_latest_checkpoint_uses_highest_numeric_step(tmp_path):
    _checkpoint(tmp_path, 9)
    expected = _checkpoint(tmp_path, 128)

    assert latest_checkpoint(tmp_path) == expected
    validate_checkpoint(expected)


def test_incomplete_checkpoint_is_rejected(tmp_path):
    checkpoint = _checkpoint(tmp_path, 12, complete=False)

    with pytest.raises(ValueError, match="optimizer.pt"):
        validate_checkpoint(checkpoint)
