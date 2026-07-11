"""Product profile boundary on top of the reusable AgentForge framework."""
from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ProductProfile:
    """User-facing product configuration.

    AgentForge code should depend on this profile for product-specific defaults
    instead of hard-coding a single app experience into framework services.
    """

    product_id: str
    display_name: str
    framework_name: str
    tagline: str
    default_template_keys: tuple[str, ...]


SODATERU_APP = ProductProfile(
    product_id="sodateru_app",
    display_name="育てるアプリ",
    framework_name="AgentForge",
    tagline="会話で作って、使いながら育てる",
    default_template_keys=(
        "calculator",
        "task_manager",
        "schedule",
        "memo",
        "household_budget",
        "translate",
        "paint",
        "retouch",
        "bluesky",
    ),
)


PRODUCTS: dict[str, ProductProfile] = {
    SODATERU_APP.product_id: SODATERU_APP,
}


def active_product() -> ProductProfile:
    product_id = os.getenv("PRODUCT_ID", SODATERU_APP.product_id).strip() or SODATERU_APP.product_id
    return PRODUCTS.get(product_id, SODATERU_APP)
