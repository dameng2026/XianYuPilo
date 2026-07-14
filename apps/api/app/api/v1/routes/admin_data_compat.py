import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....core.response import ResultObject
from ....services.sensitive_config import (
    MODEL_CONFIG_API_KEY_PURPOSE,
    decrypt_runtime_secret,
    prepare_secret_for_storage,
)
from ..deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-data-compat"])


def _dt_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _load_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _removed_feature_response(feature_name: str):
    return ResultObject.failed(f"开源版已移除{feature_name}功能", code=404)


def _model_row_to_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "modelName": row["model_name"] or "",
        "provider": row["provider_name"] or "",
        "modelType": row["scene"] or "chat",
        "baseUrl": row["base_url"] or "",
        "apiKey": "",
        "apiKeyConfigured": bool(str(row["api_key"] or "").strip()),
        "realModel": row["model_name"] or "",
        "paramsJson": {
            "maxTokens": row["max_tokens"] or 0,
            "temperature": float(row["temperature"] or 0.7),
            "imageSize": row["image_size"] or "",
            "quality": row["quality"] or "",
            "requestTimeout": 60,
        },
        "isDefault": 0,
        "status": int(row["status"] or 0),
        "remark": "",
        "updatedTime": _dt_text(row["updated_time"]),
    }


def _prompt_extra(value: Any) -> dict[str, Any]:
    payload = _load_json(value, {})
    if isinstance(payload, dict):
        return payload
    return {}


def _prompt_row_to_payload(row: dict[str, Any]) -> dict[str, Any]:
    extra = _prompt_extra(row["match_keywords"])
    return {
        "id": row["id"],
        "modelConfigId": int(row["category_key"]) if str(row["category_key"] or "").isdigit() else None,
        "promptName": row["name"] or "",
        "promptContent": row["prompt_template"] or "",
        "negativePrompt": extra.get("negativePrompt", ""),
        "paramsJson": extra.get("paramsJson"),
        "status": int(row["status"] or row["enabled"] or 0),
        "updatedTime": _dt_text(row["updated_time"]),
    }


def _sensitive_replace_to(action: Any) -> str:
    text_value = str(action or "")
    if text_value.startswith("replace:"):
        return text_value[len("replace:") :]
    return ""


def _sensitive_action(replace_to: Any) -> str:
    value = str(replace_to or "").strip()
    return f"replace:{value}" if value else "block"


def _sensitive_row_to_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "word": row["word"] or "",
        "category": row["category"] or "",
        "replaceTo": _sensitive_replace_to(row["action"]),
        "status": int(row["status"] or 0),
        "createdTime": _dt_text(row["created_time"]),
    }


@router.get("/model-config/list")
async def list_model_configs(
    scene: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    params: dict[str, Any] = {}
    where_sql = ["1 = 1"]
    if scene:
        where_sql.append("scene = :scene")
        params["scene"] = scene
    result = await db.execute(
        text(
            f"""
            SELECT id, scene, provider_name, model_name, base_url, api_key, max_tokens, temperature, image_size, quality, status, updated_time
            FROM model_config
            WHERE {' AND '.join(where_sql)}
            ORDER BY id DESC
            """
        ),
        params,
    )
    rows = result.mappings().all()
    return ResultObject.success([_model_row_to_payload(row) for row in rows])


@router.post("/model-config")
async def create_model_config(
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    model_name = str(payload.get("modelName") or "").strip()
    if not model_name:
        return ResultObject.validate_failed("模型名称不能为空")

    params_json = payload.get("paramsJson") if isinstance(payload.get("paramsJson"), dict) else {}
    await db.execute(
        text(
            """
            INSERT INTO model_config (
              scene, provider_name, model_name, base_url, api_key,
              max_tokens, temperature, image_size, quality, status,
              provider, model_type, real_model, params_json, is_default, remark, deleted, created_time
            ) VALUES (
              :scene, :provider_name, :model_name, :base_url, :api_key,
              :max_tokens, :temperature, :image_size, :quality, :status,
              :provider_name, :scene, :model_name, :params_json, :is_default, :remark, 0, NOW()
            )
            """
        ),
        {
            "scene": str(payload.get("modelType") or "chat"),
            "provider_name": str(payload.get("provider") or "").strip() or None,
            "model_name": model_name,
            "base_url": str(payload.get("baseUrl") or "").strip() or None,
            "api_key": prepare_secret_for_storage(
                incoming=payload.get("apiKey"),
                purpose=MODEL_CONFIG_API_KEY_PURPOSE,
            ),
            "max_tokens": int(params_json.get("maxTokens") or 0),
            "temperature": float(params_json.get("temperature") or 0.7),
            "image_size": str(params_json.get("imageSize") or "").strip() or None,
            "quality": str(params_json.get("quality") or "").strip() or None,
            "params_json": _dump_json(params_json),
            "is_default": int(payload.get("isDefault") or 0),
            "remark": str(payload.get("remark") or "").strip() or None,
            "status": int(payload.get("status") if payload.get("status") is not None else 1),
        },
    )
    await db.commit()
    return ResultObject.success({"success": True})


@router.put("/model-config/{model_id}")
async def update_model_config(
    model_id: int,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    params_json = payload.get("paramsJson") if isinstance(payload.get("paramsJson"), dict) else {}
    existing_result = await db.execute(
        text("SELECT api_key FROM model_config WHERE id = :id LIMIT 1"),
        {"id": model_id},
    )
    existing = existing_result.mappings().first()
    if existing is None:
        return ResultObject.failed("Model configuration does not exist", code=404)
    storage_api_key = prepare_secret_for_storage(
        incoming=payload.get("apiKey"),
        existing=existing["api_key"],
        purpose=MODEL_CONFIG_API_KEY_PURPOSE,
        clear=_as_bool(payload.get("clearApiKey")),
    )
    await db.execute(
        text(
            """
            UPDATE model_config
            SET
              scene = :scene,
              provider_name = :provider_name,
              model_name = :model_name,
              base_url = :base_url,
              api_key = :api_key,
              max_tokens = :max_tokens,
              temperature = :temperature,
              image_size = :image_size,
              quality = :quality,
              provider = :provider_name,
              model_type = :scene,
              real_model = :model_name,
              params_json = :params_json,
              is_default = :is_default,
              remark = :remark,
              status = :status
            WHERE id = :id
            """
        ),
        {
            "id": model_id,
            "scene": str(payload.get("modelType") or "chat"),
            "provider_name": str(payload.get("provider") or "").strip() or None,
            "model_name": str(payload.get("modelName") or "").strip(),
            "base_url": str(payload.get("baseUrl") or "").strip() or None,
            "api_key": storage_api_key,
            "max_tokens": int(params_json.get("maxTokens") or 0),
            "temperature": float(params_json.get("temperature") or 0.7),
            "image_size": str(params_json.get("imageSize") or "").strip() or None,
            "quality": str(params_json.get("quality") or "").strip() or None,
            "params_json": _dump_json(params_json),
            "is_default": int(payload.get("isDefault") or 0),
            "remark": str(payload.get("remark") or "").strip() or None,
            "status": int(payload.get("status") if payload.get("status") is not None else 1),
        },
    )
    await db.commit()
    return ResultObject.success({"success": True})


@router.delete("/model-config/{model_id}")
async def delete_model_config(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    await db.execute(text("DELETE FROM model_config WHERE id = :id"), {"id": model_id})
    await db.commit()
    return ResultObject.success("删除成功")


@router.post("/model-config/{model_id}/test")
async def test_model_config(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        text(
            """
            SELECT id, scene, provider_name, model_name, base_url, api_key
            FROM model_config
            WHERE id = :id
            LIMIT 1
            """
        ),
        {"id": model_id},
    )
    row = result.mappings().first()
    if row is None:
        return ResultObject.failed("模型配置不存在", code=404)
    try:
        runtime_api_key = decrypt_runtime_secret(
            row["api_key"],
            purpose=MODEL_CONFIG_API_KEY_PURPOSE,
        )
    except RuntimeError:
        logger.warning("Model configuration credential could not be decrypted: id=%s", model_id)
        return ResultObject.internal_error()
    success = bool(runtime_api_key.strip() and (row["base_url"] or "").strip())
    return ResultObject.success(
        {
            "success": success,
            "message": "配置校验通过（兼容层未发起真实调用）" if success else "缺少 API Key 或 Base URL",
            "provider": row["provider_name"] or "",
            "baseUrl": row["base_url"] or "",
            "modelName": row["model_name"] or "",
        }
    )


@router.get("/image-prompts/list")
async def list_image_prompts(
    model_config_id: int | None = Query(default=None, alias="modelConfigId"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del model_config_id, db, current_user
    return _removed_feature_response("生图类目提示词")


@router.get("/image-prompts/{prompt_id}")
async def get_image_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del prompt_id, db, current_user
    return _removed_feature_response("生图类目提示词")


@router.post("/image-prompts")
async def create_image_prompt(
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del payload, db, current_user
    return _removed_feature_response("生图类目提示词")


@router.put("/image-prompts/{prompt_id}")
async def update_image_prompt(
    prompt_id: int,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del prompt_id, payload, db, current_user
    return _removed_feature_response("生图类目提示词")


@router.delete("/image-prompts/{prompt_id}")
async def delete_image_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del prompt_id, db, current_user
    return _removed_feature_response("生图类目提示词")


@router.get("/sensitive-words/list")
async def list_sensitive_words(
    category: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del category, db, current_user
    return _removed_feature_response("敏感词策略")


@router.post("/sensitive-words")
async def create_sensitive_word(
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del payload, db, current_user
    return _removed_feature_response("敏感词策略")


@router.put("/sensitive-words/{word_id}")
async def update_sensitive_word(
    word_id: int,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del word_id, payload, db, current_user
    return _removed_feature_response("敏感词策略")


@router.delete("/sensitive-words/{word_id}")
async def delete_sensitive_word(
    word_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del word_id, db, current_user
    return _removed_feature_response("敏感词策略")


@router.post("/sensitive-words/check")
async def check_sensitive_words(
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del payload, db, current_user
    return _removed_feature_response("敏感词策略")
