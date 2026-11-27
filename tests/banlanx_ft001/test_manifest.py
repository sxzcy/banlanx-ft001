"""Release metadata and asset tests for the FT001 custom component."""

from __future__ import annotations

import json
from pathlib import Path

COMPONENT_DIR = (
    Path(__file__).resolve().parents[2] / "custom_components" / "banlanx_ft001"
)


def test_manifest_release_metadata():
    """Validate the FT001 manifest has HACS-friendly release metadata."""
    manifest = json.loads((COMPONENT_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["domain"] == "banlanx_ft001"
    assert manifest["categories"] == ["light"]
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "local_polling"
    assert manifest["integration_type"] == "device"
    assert manifest["version"] == "0.5.0"
    assert manifest["requirements"] == []
    assert manifest["dependencies"] == ["network"]


def test_brand_assets_and_translations_present():
    """Validate local HACS brand icons and translation files exist and match keys."""
    assert (COMPONENT_DIR / "brand" / "icon.png").is_file()
    assert (COMPONENT_DIR / "brand" / "icon@2x.png").is_file()

    strings = json.loads((COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
    en = json.loads(
        (COMPONENT_DIR / "translations" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (COMPONENT_DIR / "translations" / "zh-Hans.json").read_text(encoding="utf-8")
    )

    assert strings == en
    assert set(zh["config"]["step"]) == set(en["config"]["step"])
    assert set(zh["entity"]) == set(en["entity"])
    assert set(zh["entity"]["number"]) == {"channel_1_speed", "channel_2_speed"}
