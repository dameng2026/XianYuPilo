from typing import Optional, List, Any
from ..core.camel import CamelModel


class ItemListReqDTO(CamelModel):
    tenant_id: Optional[int] = None
    xianyu_account_id: Optional[int] = None
    page_num: Optional[int] = 1
    page_size: Optional[int] = 20


class ItemReqDTO(CamelModel):
    tenant_id: Optional[int] = None
    xianyu_account_id: Optional[int] = None
    xy_goods_id: Optional[str] = None


class ItemDTO(CamelModel):
    id: Optional[int] = None
    xianyu_account_id: Optional[int] = None
    xy_goods_id: Optional[str] = None
    goods_title: Optional[str] = None
    goods_price: Optional[str] = None
    goods_stock: Optional[int] = None
    goods_image: Optional[str] = None
    cover_pic: Optional[str] = None
    sold_price: Optional[str] = None
    quantity: Optional[int] = None
    exposure_count: Optional[int] = None
    view_count: Optional[int] = None
    want_count: Optional[int] = None
    detail_url: Optional[str] = None
    detail_info: Optional[str] = None
    sort_order: Optional[int] = None
    status: Optional[int] = None
    created_time: Optional[str] = None


class ItemListRespDTO(CamelModel):
    items: List[ItemDTO] = []
    total: int = 0


class ItemDetailRespDTO(CamelModel):
    item: Optional[ItemDTO] = None


class RefreshItemsRespDTO(CamelModel):
    message: str = "刷新成功"


class DeleteItemRespDTO(CamelModel):
    message: str = "删除成功"


class ItemOperateReqDTO(CamelModel):
    """商品操作请求（下架/删除等）"""
    tenant_id: Optional[int] = None
    xianyu_account_id: Optional[int] = None
    xy_goods_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class ItemBatchOperateReqDTO(CamelModel):
    """批量商品操作请求"""
    tenant_id: Optional[int] = None
    xianyu_account_id: Optional[int] = None
    item_ids: List[str] = []


class UpdateItemPriceReqDTO(CamelModel):
    """改价请求"""
    tenant_id: Optional[int] = None
    xianyu_account_id: Optional[int] = None
    xy_goods_id: Optional[str] = None
    price: Optional[str] = None
    idempotency_key: Optional[str] = None


class AutoDeliveryConfigReqDTO(CamelModel):
    xianyu_account_id: int
    xy_goods_id: Optional[str] = None
    delivery_type: Optional[str] = None
    delivery_content: Optional[str] = None


class AutoDeliveryConfigRespDTO(CamelModel):
    id: Optional[int] = None
    xianyu_account_id: Optional[int] = None
    xy_goods_id: Optional[str] = None
    delivery_type: Optional[str] = None
    delivery_content: Optional[str] = None
    status: Optional[int] = None


class TriggerAutoDeliveryReqDTO(CamelModel):
    xianyu_account_id: int
    xy_goods_id: Optional[str] = None
    order_id: Optional[str] = None


class AutoReplyRuleReqDTO(CamelModel):
    xianyu_account_id: int
    xy_goods_id: Optional[str] = None
    rule_name: Optional[str] = None
    match_type: Optional[str] = None
    match_keywords: Optional[str] = None
    reply_content: Optional[str] = None


class AutoReplyRuleRespDTO(CamelModel):
    id: Optional[int] = None
    xianyu_account_id: Optional[int] = None
    xy_goods_id: Optional[str] = None
    rule_name: Optional[str] = None
    match_type: Optional[str] = None
    match_keywords: Optional[str] = None
    reply_content: Optional[str] = None
    status: Optional[int] = None


class KamiConfigReqDTO(CamelModel):
    xianyu_account_id: int
    xy_goods_id: Optional[str] = None
    config_name: Optional[str] = None
    delivery_type: Optional[str] = None


class KamiConfigRespDTO(CamelModel):
    id: Optional[int] = None
    xianyu_account_id: Optional[int] = None
    xy_goods_id: Optional[str] = None
    config_name: Optional[str] = None
    delivery_type: Optional[str] = None


class KamiItemReqDTO(CamelModel):
    kami_config_id: int
    kami_content: str


class KamiItemRespDTO(CamelModel):
    id: Optional[int] = None
    kami_config_id: Optional[int] = None
    kami_content: Optional[str] = None
    status: Optional[int] = None


class KamiBatchImportReqDTO(CamelModel):
    kami_config_id: int
    kami_list: List[str] = []


class SaveSettingReqDTO(CamelModel):
    setting_key: str
    setting_value: str


class GetSettingReqDTO(CamelModel):
    setting_key: str


class GetSettingRespDTO(CamelModel):
    setting_key: Optional[str] = None
    setting_value: Optional[str] = None
    configured: Optional[bool] = None


class MsgListReqDTO(CamelModel):
    xianyu_account_id: Optional[int] = None
    session_id: Optional[str] = None
    page_num: Optional[int] = 1
    page_size: Optional[int] = 20
    tenant_id: Optional[int] = None


class MsgDTO(CamelModel):
    id: Optional[int] = None
    xianyu_account_id: Optional[int] = None
    session_id: Optional[str] = None
    from_user_id: Optional[str] = None
    to_user_id: Optional[str] = None
    content: Optional[str] = None
    message_type: Optional[str] = None
    direction: Optional[str] = None
    created_time: Optional[str] = None


class AiProviderReqDTO(CamelModel):
    provider_name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None


class AiProviderRespDTO(CamelModel):
    id: Optional[int] = None
    provider_name: Optional[str] = None
    api_key: Optional[str] = None
    api_key_configured: bool = False
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    status: Optional[int] = None
