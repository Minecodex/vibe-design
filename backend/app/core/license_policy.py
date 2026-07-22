from typing import Literal

from app.core.license import LicenseEdition

LicenseCapability = Literal[
    "home_agent",
    "canvas_plugins",
    "prompt_extractor",
    "photoshop_edit",
    "photoshop_plugin_save",
]

LICENSE_CAPABILITY_BY_EDITION: dict[LicenseEdition, dict[LicenseCapability, bool]] = {
    "premium": {
        "home_agent": False,
        "canvas_plugins": False,
        "prompt_extractor": False,
        "photoshop_edit": False,
        "photoshop_plugin_save": False,
    },
    "flagship": {
        "home_agent": True,
        "canvas_plugins": True,
        "prompt_extractor": True,
        "photoshop_edit": True,
        "photoshop_plugin_save": True,
    },
}


def license_capability_enabled(edition: LicenseEdition | None, capability: LicenseCapability) -> bool:
    if edition is None:
        return False
    return LICENSE_CAPABILITY_BY_EDITION.get(edition, {}).get(capability, False)
