"""快捷回复模板 CRUD 路由。

与自动回复规则（auto_reply_rule）解耦，专用于"人工点击即插入到输入框"的常用语。
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....models.entities import QuickReplyTemplate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quickReplyTemplate", tags=["快捷回复模板"])


class TemplateSaveRequest(BaseModel):
    id: int | None = None
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    sort_order: int = 0


def _template_to_dict(t: QuickReplyTemplate) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "content": t.content,
        "sortOrder": t.sort_order,
        "status": t.status,
        "createdAt": t.created_time.isoformat() if t.created_time else None,
        "updatedAt": t.updated_time.isoformat() if t.updated_time else None,
    }


@router.get("/list")
async def list_templates(
    request: Request,
    size: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """列出快捷回复模板（按 sort_order, id 排序）。"""
    account_id = _account_id_from_request(request)
    # 查询：当前账号专属 + 全租户通用（account_id IS NULL）
    sql = text("""
        SELECT * FROM quick_reply_template
        WHERE deleted = 0
          AND (account_id IS NULL OR account_id = :account_id)
        ORDER BY sort_order ASC, id ASC
        LIMIT :size
    """)
    rows = await db.execute(sql, {
        "account_id": account_id,
        "size": min(max(size, 1), 500),
    })
    items = [dict(row) for row in rows.mappings().all()]
    return {"code": 200, "data": {"records": items, "total": len(items)}}


@router.post("/save")
async def save_template(
    body: TemplateSaveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """新增或更新快捷回复模板。id 为空时新增，否则更新。"""
    account_id = _account_id_from_request(request)

    if body.id:
        # 更新
        result = await db.execute(
            text("""
                UPDATE quick_reply_template
                SET title = :title, content = :content, sort_order = :sort_order, updated_time = NOW()
                WHERE id = :id AND deleted = 0
            """),
            {
                "id": body.id,
                "title": body.title.strip(),
                "content": body.content.strip(),
                "sort_order": body.sort_order,
            }
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="模板不存在或无权修改")
        await db.commit()
        return {"code": 200, "data": {"id": body.id}, "message": "更新成功"}

    # 新增
    result = await db.execute(
        text("""
            INSERT INTO quick_reply_template (account_id, title, content, sort_order, status, deleted, created_time, updated_time)
            VALUES (:account_id, :title, :content, :sort_order, 1, 0, NOW(), NOW())
        """),
        {
            "account_id": account_id,
            "title": body.title.strip(),
            "content": body.content.strip(),
            "sort_order": body.sort_order,
        }
    )
    await db.commit()
    new_id = result.lastrowid
    return {"code": 200, "data": {"id": new_id}, "message": "添加成功"}


@router.post("/delete")
async def delete_template(
    request: Request,
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """软删除快捷回复模板。"""
    pass  # account_id not needed here
    result = await db.execute(
        text("""
            UPDATE quick_reply_template SET deleted = 1, updated_time = NOW()
            WHERE id = :id
        """),
        {"id": id}
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="模板不存在或无权删除")
    await db.commit()
    return {"code": 200, "message": "删除成功"}


@router.post("/initDefaults")
async def init_default_templates(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """初始化 10 条默认快捷回复模板（仅当当前租户无模板时执行）。"""
    account_id = _account_id_from_request(request)

    # 检查是否已有模板
    check = await db.execute(
        text("SELECT COUNT(*) AS cnt FROM quick_reply_template WHERE deleted = 0")
    )
    existing = check.scalar() or 0
    if existing > 0:
        return {"code": 200, "message": f"已存在 {existing} 条模板，跳过初始化", "data": {"skipInit": True}}

    defaults = [
        ("亲切问候", "您好，很高兴为您服务！有什么可以帮您的吗？", 1),
        ("商品咨询", "这款商品目前有货的，您可以放心下单，我们会在24小时内发货。", 2),
        ("价格说明", "亲，这是我们的实价哦，品质保证，性价比很高。如需优惠可以关注店铺活动~", 3),
        ("发货时效", "下单后我们会在24小时内安排发货，一般2-3天可以送达，请耐心等待~", 4),
        ("物流查询", "您好，我帮您查一下物流信息，请稍等。如有问题随时联系我们。", 5),
        ("售后保障", "我们提供7天无理由退换货服务，商品有质量问题可以随时联系我们处理。", 6),
        ("催付提醒", "亲，您看中的宝贝还没下单哦，库存有限，喜欢就尽快下单吧~", 7),
        ("结束语", "感谢您的咨询，祝您生活愉快！如有其他问题欢迎随时联系我们~", 8),
        ("议价回复", "亲，我们的价格已经很实惠了，但您可以关注店铺后续活动，会有更多优惠哦~", 9),
        ("加微引导", "抱歉亲，平台规定不能交换联系方式哦，有问题可以在这里直接沟通，我们会尽快回复您~", 10),
    ]

    for title, content, sort_order in defaults:
        await db.execute(
            text("""
                INSERT INTO quick_reply_template (account_id, title, content, sort_order, status, deleted, created_time, updated_time)
                VALUES (:account_id, :title, :content, :sort_order, 1, 0, NOW(), NOW())
            """),
            {
                "account_id": None,  # 默认模板设为全租户通用
                "title": title,
                "content": content,
                "sort_order": sort_order,
            }
        )
    await db.commit()
    return {"code": 200, "message": f"已初始化 {len(defaults)} 条默认模板", "data": {"count": len(defaults)}}
