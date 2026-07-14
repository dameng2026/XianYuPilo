from typing import Optional
from ..core.camel import CamelModel


class DashboardStatsRespDTO(CamelModel):
    account_count: int = 0
    item_count: int = 0
    selling_item_count: int = 0
    off_shelf_item_count: int = 0
    sold_item_count: int = 0
    delivery_success_count: int = 0
    delivery_fail_count: int = 0
    pending_delivery_count: int = 0