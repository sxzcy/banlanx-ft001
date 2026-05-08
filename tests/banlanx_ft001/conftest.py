"""Test helpers for the BanlanX FT001 integration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT_DIR = ROOT / "custom_components" / "banlanx_ft001"


@pytest.fixture
def component_modules() -> dict[str, types.ModuleType]:
    """Load protocol modules without requiring Home Assistant to be installed."""
    ha = types.ModuleType("homeassistant")
    ha_const = types.ModuleType("homeassistant.const")

    class Platform:
        LIGHT = "light"

    ha_const.Platform = Platform
    sys.modules.setdefault("homeassistant", ha)
    sys.modules.setdefault("homeassistant.const", ha_const)
    sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))

    package = types.ModuleType("custom_components.banlanx_ft001")
    package.__path__ = [str(COMPONENT_DIR)]
    sys.modules["custom_components.banlanx_ft001"] = package

    modules: dict[str, types.ModuleType] = {}
    for name in ("const", "client", "discovery"):
        spec = importlib.util.spec_from_file_location(
            f"custom_components.banlanx_ft001.{name}",
            COMPONENT_DIR / f"{name}.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        modules[name] = module
    return modules
