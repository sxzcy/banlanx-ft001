"""Release metadata tests for the FT001 custom component."""

from __future__ import annotations

import json
from pathlib import Path


def test_manifest_release_metadata():
    """Validate the FT001 manifest has HACS-friendly release metadata."""
    manifest = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "custom_components"
            / "banlanx_ft001"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )

    assert manifest["domain"] == "banlanx_ft001"
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "local_polling"
    assert manifest["integration_type"] == "device"
    assert manifest["version"] == "0.4.0"
    assert manifest["requirements"] == []
