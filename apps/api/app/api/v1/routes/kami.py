import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ....core.database import get_db
from ....core.response import ResultObject
from ....models.entities import CardGroup, CardItem
from ....schemas.common import (
    KamiConfigReqDTO, KamiConfigRespDTO, KamiItemReqDTO, KamiItemRespDTO,
    KamiBatchImportReqDTO
)
from ..deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kami")


def _group_to_dto(group: CardGroup) -> KamiConfigRespDTO:
    return KamiConfigRespDTO(
        id=group.id,
        xianyu_account_id=None,
        xy_goods_id=None,
        config_name=group.group_name,
        delivery_type=group.group_type,
    )


def _item_to_dto(item: CardItem) -> KamiItemRespDTO:
    return KamiItemRespDTO(
        id=item.id,
        kami_config_id=item.group_id,
        kami_content=item.card_key,
        status=1 if item.is_used else 0,
    )


async def _refresh_group_counts(db: AsyncSession, group_id: int):
    total = (await db.execute(
        select(func.count()).select_from(CardItem).where(CardItem.group_id == group_id, CardItem.deleted == 0)
    )).scalar() or 0
    used = (await db.execute(
        select(func.count()).select_from(CardItem).where(CardItem.group_id == group_id, CardItem.deleted == 0, CardItem.is_used == 1)
    )).scalar() or 0
    group = (await db.execute(select(CardGroup).where(CardGroup.id == group_id))).scalar_one_or_none()
    if group:
        group.total_count = total
        group.used_count = used
        group.available_count = max(total - used, 0)


@router.post("/config/list", response_model=ResultObject[list])
async def list_kami_configs(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        result = await db.execute(
            select(CardGroup).where(CardGroup.deleted == 0)
            .order_by(CardGroup.id.desc())
        )
        configs = result.scalars().all()
        return ResultObject.success([_group_to_dto(c) for c in configs])
    except Exception as e:
        logger.error("获取卡密配置失败", exc_info=True)
        return ResultObject.internal_error()


@router.post("/config/save", response_model=ResultObject[str])
async def save_kami_config(
    req: KamiConfigReqDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        config = CardGroup(
            group_name=req.config_name or "默认卡密组",
            group_type=req.delivery_type or "kami",
            status=1,
            deleted=0,
        )
        db.add(config)
        await db.commit()
        return ResultObject.success("保存成功")
    except Exception as e:
        logger.error("保存卡密配置失败", exc_info=True)
        return ResultObject.internal_error()


@router.post("/item/list", response_model=ResultObject[list])
async def list_kami_items(
    req: KamiItemReqDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        result = await db.execute(
            select(CardItem).where(
                CardItem.group_id == req.kami_config_id,
                CardItem.deleted == 0,
            ).order_by(CardItem.id.desc())
        )
        items = result.scalars().all()
        return ResultObject.success([_item_to_dto(i) for i in items])
    except Exception as e:
        logger.error("获取卡密列表失败", exc_info=True)
        return ResultObject.internal_error()


@router.post("/item/add", response_model=ResultObject[str])
async def add_kami_item(
    req: KamiItemReqDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        item = CardItem(
            group_id=req.kami_config_id,
            card_key=req.kami_content,
            is_used=0,
            deleted=0,
        )
        db.add(item)
        await _refresh_group_counts(db, req.kami_config_id)
        await db.commit()
        return ResultObject.success("添加成功")
    except Exception as e:
        logger.error("添加卡密失败", exc_info=True)
        return ResultObject.internal_error()


@router.post("/item/batchImport", response_model=ResultObject[str])
async def batch_import_kami(
    req: KamiBatchImportReqDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        for content in req.kami_list:
            item = CardItem(
                group_id=req.kami_config_id,
                card_key=content,
                is_used=0,
                deleted=0,
            )
            db.add(item)
        await _refresh_group_counts(db, req.kami_config_id)
        await db.commit()
        return ResultObject.success(f"批量导入成功，共导入{len(req.kami_list)}条")
    except Exception as e:
        logger.error("批量导入卡密失败", exc_info=True)
        return ResultObject.internal_error()
