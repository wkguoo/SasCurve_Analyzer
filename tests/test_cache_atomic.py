from pathlib import Path

import pytest

from app.core.auto_batch_schema import AutoBatchRun
from app.core.batch_cache import load_run_checkpoint, save_run_checkpoint


def test_interrupted_checkpoint_replace_preserves_last_complete_record(tmp_path, monkeypatch):
    first = AutoBatchRun(batch_id="sample", status="completed")
    save_run_checkpoint(tmp_path, first)
    original = (tmp_path / "run_checkpoint.json").read_bytes()
    original_replace = Path.replace
    def fail_checkpoint(path, destination):
        if Path(destination).name == "run_checkpoint.json":
            raise OSError("interrupted replacement")
        return original_replace(path, destination)
    monkeypatch.setattr(Path, "replace", fail_checkpoint)
    with pytest.raises(OSError, match="interrupted replacement"):
        save_run_checkpoint(tmp_path, AutoBatchRun(batch_id="sample", status="cancelled"))
    assert (tmp_path / "run_checkpoint.json").read_bytes() == original
    assert load_run_checkpoint(tmp_path).status == "completed"
