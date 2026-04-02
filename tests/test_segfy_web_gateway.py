from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

from rpa_corretora.integrations.segfy_web_gateway import CascadingSegfyGateway, SegfyWebGateway


class _Gateway:
    def __init__(self, imported: int) -> None:
        self.imported = imported

    def import_documents(self) -> int:
        return self.imported

    def fetch_policy_data(self):
        return []

    def register_payment(self, *, commitment_id: str, description: str) -> bool:
        _ = (commitment_id, description)
        return False


def test_segfy_web_gateway_collects_supported_files_with_limit(tmp_path: Path) -> None:
    source_dir = tmp_path / "import"
    source_dir.mkdir()
    (source_dir / "b.xlsx").write_text("x", encoding="utf-8")
    (source_dir / "a.pdf").write_text("x", encoding="utf-8")
    (source_dir / "c.csv").write_text("x", encoding="utf-8")
    (source_dir / "ignore.txt").write_text("x", encoding="utf-8")

    gateway = SegfyWebGateway(
        username="u",
        password="p",
        base_url="https://app.segfy.com",
        import_source_dir=source_dir,
        import_max_files=2,
    )

    files = gateway._collect_import_files()
    assert len(files) == 2
    assert [item.name for item in files] == ["a.pdf", "b.xlsx"]


def test_cascading_segfy_gateway_import_uses_fallback_when_primary_zero() -> None:
    cascading = CascadingSegfyGateway(
        primary=_Gateway(imported=0),
        fallback=_Gateway(imported=3),
    )
    assert cascading.import_documents() == 3


def test_segfy_web_gateway_filters_files_newer_than_last_execution(tmp_path: Path) -> None:
    source_dir = tmp_path / "import"
    source_dir.mkdir()
    state_path = tmp_path / "state.json"

    old_file = source_dir / "old.pdf"
    new_file = source_dir / "new.xlsx"
    old_file.write_text("old", encoding="utf-8")
    new_file.write_text("new", encoding="utf-8")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=1)
    old_ts = (cutoff - timedelta(hours=1)).timestamp()
    new_ts = (cutoff + timedelta(hours=1)).timestamp()
    os.utime(old_file, (old_ts, old_ts))
    os.utime(new_file, (new_ts, new_ts))

    gateway = SegfyWebGateway(
        username="u",
        password="p",
        base_url="https://app.segfy.com",
        import_source_dir=source_dir,
        import_state_path=state_path,
    )
    gateway._save_last_execution_utc(cutoff)
    loaded_cutoff = gateway._load_last_execution_utc()

    files = gateway._collect_import_files(modified_after=loaded_cutoff)
    assert [item.name for item in files] == ["new.xlsx"]


def test_segfy_web_gateway_persists_last_execution_state(tmp_path: Path) -> None:
    gateway = SegfyWebGateway(
        username="u",
        password="p",
        base_url="https://app.segfy.com",
        import_source_dir=tmp_path,
        import_state_path=tmp_path / "segfy_state.json",
    )
    marker = datetime(2026, 4, 1, 20, 0, tzinfo=timezone.utc)
    gateway._save_last_execution_utc(marker)

    loaded = gateway._load_last_execution_utc()
    assert loaded == marker
