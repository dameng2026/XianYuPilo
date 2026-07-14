"""
自动分类 API 路由
提供图片上传后自动识别分类的接口
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, Body, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ....core.database import get_db
from ....core.response import ResultObject
from ....core.upload_security import (
    UnsafePathError,
    UnsafeRemoteURLError,
    UploadValidationError,
    download_public_image,
    load_safe_local_image,
    normalize_image_bytes,
    read_upload_limited,
    resolve_upload_path,
)
from ....core.cookie_crypto import decrypt_cookie_if_needed
from ....core.config import settings
from ....models.entities import XianyuAccount, XianyuAccountAuth
from ....services.auto_category import auto_category as auto_category_service, _get_token_from_cookie
from ....services.category_data import CategoryDataError, load_categories
from ..deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/xianyu/accounts", tags=["autoCategory"])


async def _resolve_image_data(url: str) -> bytes:
    """
    将图片 URL 解析为二进制数据。

    仅支持两种安全场景：
    1. 公网 HTTPS URL：固定到校验过的公网 IP 后限量下载；
    2. /uploads 相对路径：经目录 containment 与栅格图片校验后读取。
    """
    value = str(url or "").strip()
    if value.startswith("/uploads/"):
        local_path = resolve_upload_path(value.removeprefix("/uploads/"))
        data, _ = await asyncio.to_thread(load_safe_local_image, local_path)
        return data
    if value.startswith("/"):
        raise UnsafePathError("本地图片必须位于 /uploads 目录")
    return await download_public_image(value)


async def _get_account_cookie(db: AsyncSession, account_id: int) -> Optional[str]:
    """获取指定账号的最新有效解密 Cookie（按更新时间倒序取最近一条）"""
    result = await db.execute(
        select(XianyuAccountAuth).where(
            XianyuAccountAuth.account_id == account_id,
            XianyuAccountAuth.deleted == 0,
            XianyuAccountAuth.cookie_status == 1,
            XianyuAccountAuth.last_login_status_code == "OK",
            XianyuAccountAuth.encrypted_cookie.isnot(None),
            XianyuAccountAuth.encrypted_cookie != "",
        ).order_by(XianyuAccountAuth.updated_time.desc()).limit(1)
    )
    auth = result.scalar_one_or_none()
    if not auth or not auth.encrypted_cookie:
        return None
    return decrypt_cookie_if_needed(auth.encrypted_cookie)


@router.post("/{account_id}/auto-category")
async def auto_category(
    account_id: int,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    根据封面图 URL 自动识别分类。

    请求体:
    {
        "coverImageUrl": "https://xxx.com/a.jpg",   # 必填
        "title": "可选，商品标题",
        "description": "可选，商品描述"
    }
    """
    request_id = body.get("requestId", "")

    try:
        cover_image_url = (body.get("coverImageUrl") or "").strip()
        if not cover_image_url:
            return ResultObject.validate_failed("coverImageUrl 不能为空")

        title = (body.get("title") or "").strip() or None
        description = (body.get("description") or "").strip() or None

        # 获取账号 Cookie
        cookie_str = await _get_account_cookie(db, account_id)
        if not cookie_str:
            logger.warning("账号未登录或Cookie已失效: account_id=%d", account_id)
            return ResultObject.success({
                "success": False,
                "source": "manual",
                "autoSelected": False,
                "selectedCategory": None,
                "candidates": [],
                "cdnImageUrl": None,
                "fallbackRequired": True,
                "fallbackReason": "COOKIE_EXPIRED",
            })

        # 下载/读取封面图
        try:
            image_data = await _resolve_image_data(cover_image_url)
        except (UnsafePathError, UnsafeRemoteURLError, UploadValidationError, OSError):
            logger.warning("自动分类封面图不可用 accountId=%d", account_id, exc_info=True)
            return ResultObject.success({
                "success": False,
                "source": "local_category",
                "autoSelected": False,
                "selectedCategory": None,
                "candidates": [],
                "cdnImageUrl": None,
                "fallbackRequired": True,
                "fallbackReason": "UPLOAD_FAILED",
            })

        # 执行自动分类（该函数内部有完整的错误处理，永远返回 dict）
        result = await asyncio.to_thread(
            auto_category_service,
            cookie_str=cookie_str,
            image_data=image_data,
            title=title,
            description=description,
        )

        return ResultObject.success(result)

    except Exception:
        logger.exception("自动分类路由未捕获异常 accountId=%d", account_id)
        return ResultObject.success({
            "success": False,
            "source": "manual",
            "autoSelected": False,
            "selectedCategory": None,
            "candidates": [],
            "cdnImageUrl": None,
            "fallbackRequired": True,
            "fallbackReason": "INTERNAL_ERROR",
        })


@router.post("/{account_id}/auto-category/upload")
async def auto_category_upload(
    account_id: int,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    上传封面图文件并自动识别分类。
    使用 multipart/form-data 上传。
    """
    try:
        if not file:
            return ResultObject.validate_failed("文件不能为空")

        # 获取账号 Cookie
        cookie_str = await _get_account_cookie(db, account_id)
        if not cookie_str:
            logger.warning("账号未登录或Cookie已失效: account_id=%d", account_id)
            return ResultObject.success({
                "success": False,
                "source": "manual",
                "autoSelected": False,
                "selectedCategory": None,
                "candidates": [],
                "cdnImageUrl": None,
                "fallbackRequired": True,
                "fallbackReason": "COOKIE_EXPIRED",
            })

        # 有界读取并重新编码，拒绝压缩炸弹、伪装格式与多态载荷。
        uploaded = await read_upload_limited(file)
        image_data, _, _ = await asyncio.to_thread(normalize_image_bytes, uploaded)

        # 执行自动分类
        result = await asyncio.to_thread(
            auto_category_service,
            cookie_str=cookie_str,
            image_data=image_data,
            title=title,
            description=description,
        )

        return ResultObject.success(result)

    except (UploadValidationError, OSError):
        logger.warning("自动分类上传图片无效 accountId=%d", account_id, exc_info=True)
        return ResultObject.success({
            "success": False,
            "source": "manual",
            "autoSelected": False,
            "selectedCategory": None,
            "candidates": [],
            "cdnImageUrl": None,
            "fallbackRequired": True,
            "fallbackReason": "UPLOAD_FAILED",
        })
    except Exception:
        logger.exception("自动分类上传路由未捕获异常: account_id=%d", account_id)
        return ResultObject.success({
            "success": False,
            "source": "manual",
            "autoSelected": False,
            "selectedCategory": None,
            "candidates": [],
            "cdnImageUrl": None,
            "fallbackRequired": True,
            "fallbackReason": "INTERNAL_ERROR",
        })


@router.get("/auto-category/config")
async def auto_category_config():
    """
    获取自动分类系统配置状态。
    返回 appKey 状态和当前阈值配置。
    """
    return ResultObject.success({
        "appKeyConfigured": bool(settings.xianyu_mtop_app_key),
        "appKeyPreview": settings.xianyu_mtop_app_key[:4] + "****" if settings.xianyu_mtop_app_key else "",
        "minScore": settings.auto_category_min_score,
        "minMargin": settings.auto_category_min_margin,
        "categoryApi": settings.xianyu_mtop_category_api,
    })


# ---- 分类树管理（非账号相关） ----
categories_router = APIRouter(prefix="/xianyu/categories", tags=["categories"])


@categories_router.get("")
async def get_categories():
    """
    获取完整分类树。
    返回与前端 categories.json 兼容的树结构。
    """
    try:
        data = await asyncio.to_thread(load_categories)
        tree = data.get("cation", data.get("categories", []))
        return ResultObject.success({"cation": tree})
    except CategoryDataError:
        logger.error("获取分类树失败", exc_info=True)
        return ResultObject.internal_error("分类树暂不可用，请稍后重试")


@categories_router.post("/sync")
async def sync_categories(body: dict = Body(...)):
    """Retired: application source files are immutable at runtime."""

    del body
    raise HTTPException(
        status_code=410,
        detail=(
            "运行时分类树写入已移除：自动分类候选会直接返回供本次选择，"
            "基础分类树必须随版本发布，不能由 API 副本修改应用文件。"
        ),
    )
