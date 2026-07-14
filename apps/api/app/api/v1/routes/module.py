"""
通用模块元数据路由（开源版精简）
================================
仅提供模块元数据查询端点。具体 CRUD 由各专用路由处理：
- system.py / delivery_workflow_compat.py / admin_data_compat.py
- frontend_compat.py（真实审计日志只读查询）/ scheduled_task.py / rag.py 等

开源版已移除生图类目提示词、敏感词策略等旧导航页面，这里只保留仍然可用的模块元数据入口。
"""
import logging

from fastapi import APIRouter, Depends

from ....core.response import ResultObject
from ....services.module_catalog import get_module, list_modules
from ..deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/modules", tags=["module"])


@router.get("")
@router.get("/")
async def list_all_modules(
    current_user: dict = Depends(get_current_user),
):
    """列出所有可用模块元数据。"""
    try:
        modules = [m.to_dict() for m in list_modules()]
        return ResultObject.success(modules)
    except Exception as e:
        logger.error("列出模块元数据失败", exc_info=True)
        return ResultObject.internal_error()


@router.get("/{module_key}/meta")
async def get_module_meta(
    module_key: str,
    current_user: dict = Depends(get_current_user),
):
    """获取单个模块元数据（字段定义）。"""
    try:
        meta = get_module(module_key)
        if not meta:
            return ResultObject.failed(f"未知的模块: {module_key}")
        return ResultObject.success(meta.to_dict())
    except Exception as e:
        logger.error("获取模块元数据失败 module=%s", module_key, exc_info=True)
        return ResultObject.internal_error()
