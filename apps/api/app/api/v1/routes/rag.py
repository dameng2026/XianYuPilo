"""
RAG 知识库路由（开源版）
========================
对应三张表：
- rag_knowledge_base - 知识库元数据
- rag_document       - 文档元数据
- rag_chunk          - 文档分块 + 向量（JSON 序列化存储）

向量检索使用纯 Python 余弦相似度（适合中小规模，<10万 chunks）。
Embedding 生成复用 app.services.rag_service.generate_embedding / split_text。
AI 生成复用 app.services.ai_provider.generate_text。

支持的文档类型：.txt / .md（直接 decode）；其他类型仅记录元数据，content 由调用方提供。
"""
import asyncio
import io
import json
import logging
import math
import re
import unicodedata
import uuid
from datetime import datetime
from pathlib import PurePath
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....core.config import settings
from ....core.response import ResultObject
from ....core.upload_security import (
    UnsafeRemoteURLError,
    UploadValidationError,
    read_upload_limited,
    validate_public_https_url,
)
from ....core.camel import CamelModel
from ....models.entities import RagKnowledgeBase, RagDocument, RagChunk
from ....services.sensitive_config import (
    RAG_EMBEDDING_API_KEY_PURPOSE,
    decrypt_runtime_secret,
    prepare_secret_for_storage,
)
from ..deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rag", tags=["rag"])


# 复用 rag_service 的切片与向量化能力
try:
    from ....services.rag_service import split_text as _split_text
    from ....services.embedding_runtime import generate_embedding as _generate_embedding
    _RAG_SERVICE_AVAILABLE = True
except Exception:
    logger.warning("rag_service 不可用，RAG 文档索引功能将受限")
    _RAG_SERVICE_AVAILABLE = False
    _split_text = None
    _generate_embedding = None

try:
    from ....services.ai_provider import generate_text as _ai_generate_text
    _AI_AVAILABLE = True
except Exception:
    _AI_AVAILABLE = False
    _ai_generate_text = None


MAX_UPLOAD_SIZE = settings.max_rag_document_bytes
ALLOWED_TEXT_EXTS = {".txt", ".md", ".markdown"}
DEFAULT_TOP_K = 5
DEFAULT_SIMILARITY_THRESHOLD = 0.3
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 80


def _safe_document_name(value: str | None, *, fallback: str) -> str:
    raw = unicodedata.normalize("NFKC", str(value or "")).replace("\\", "/")
    name = PurePath(raw).name.strip()
    name = re.sub(r"[\x00-\x1f\x7f<>:\"/\\|?*]", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = fallback
    if len(name) > 180:
        extension = _get_extension(name)
        name = f"{name[: 180 - len(extension)]}{extension}"
    return name


# ============================================================
# Schemas
# ============================================================
class KnowledgeBaseDTO(CamelModel):
    id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_api_key_configured: bool = False
    embedding_base_url: Optional[str] = None
    doc_count: Optional[int] = 0
    chunk_count: Optional[int] = 0
    status: Optional[int] = 1
    created_time: Optional[str] = None
    updated_time: Optional[str] = None


class KnowledgeBaseUpsertDTO(CamelModel):
    name: str
    description: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_api_key: Optional[str] = None
    clear_embedding_api_key: bool = False
    embedding_base_url: Optional[str] = None
    status: Optional[int] = 1


class DocumentDTO(CamelModel):
    id: Optional[int] = None
    kb_id: Optional[int] = None
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    file_type: Optional[str] = None
    file_size: Optional[int] = 0
    chunk_count: Optional[int] = 0
    parse_status: Optional[str] = None
    error_message: Optional[str] = None
    created_time: Optional[str] = None
    updated_time: Optional[str] = None


class ChunkDTO(CamelModel):
    id: Optional[int] = None
    kb_id: Optional[int] = None
    doc_id: Optional[int] = None
    chunk_index: Optional[int] = None
    content: Optional[str] = None
    token_count: Optional[int] = 0
    created_time: Optional[str] = None


class SearchReqDTO(CamelModel):
    query: str
    top_k: Optional[int] = DEFAULT_TOP_K
    similarity_threshold: Optional[float] = DEFAULT_SIMILARITY_THRESHOLD


class SearchHitDTO(CamelModel):
    chunk_id: Optional[int] = None
    doc_id: Optional[int] = None
    content: Optional[str] = None
    score: Optional[float] = None


class ChatReqDTO(CamelModel):
    query: str
    knowledge_base_ids: List[int] = []
    top_k: Optional[int] = DEFAULT_TOP_K
    similarity_threshold: Optional[float] = DEFAULT_SIMILARITY_THRESHOLD
    system_prompt: Optional[str] = None


class ChatRespDTO(CamelModel):
    answer: str = ""
    hits: List[SearchHitDTO] = []
    hit_count: int = 0


# ============================================================
# Helpers
# ============================================================
def preserve_embedding_api_key(incoming_key: Optional[str], existing_key: Optional[str]) -> Optional[str]:
    """Keep the stored key when the edit form submits its masked empty value."""
    if incoming_key is None or not incoming_key.strip():
        return existing_key
    return incoming_key


async def _validated_embedding_base_url(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        return await asyncio.to_thread(validate_public_https_url, normalized)
    except UnsafeRemoteURLError as exc:
        raise HTTPException(
            status_code=422,
            detail="向量模型地址必须是可解析的公网 HTTPS 地址，且不得指向本机或内网",
        ) from exc


def _embedding_origin(value: Optional[str]) -> tuple[str, str, int] | None:
    from urllib.parse import urlparse

    parsed = urlparse(str(value or "").strip())
    if not parsed.scheme or not parsed.hostname:
        return None
    try:
        port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
    except ValueError:
        return None
    return parsed.scheme.casefold(), parsed.hostname.rstrip(".").casefold(), port


def _kb_to_dto(kb: RagKnowledgeBase) -> KnowledgeBaseDTO:
    return KnowledgeBaseDTO(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        embedding_model=kb.embedding_model,
        embedding_api_key="",
        embedding_api_key_configured=bool((kb.embedding_api_key or "").strip()),
        embedding_base_url=kb.embedding_base_url,
        doc_count=kb.doc_count,
        chunk_count=kb.chunk_count,
        status=kb.status,
        created_time=str(kb.created_time) if kb.created_time else None,
        updated_time=str(kb.updated_time) if kb.updated_time else None,
    )


def _knowledge_base_embedding_runtime_config(
    kb: RagKnowledgeBase,
) -> dict[str, str] | None:
    api_key = decrypt_runtime_secret(
        kb.embedding_api_key,
        purpose=RAG_EMBEDDING_API_KEY_PURPOSE,
    )
    config = {
        "base_url": str(kb.embedding_base_url or "").strip(),
        "api_key": api_key.strip(),
        "model": str(kb.embedding_model or "").strip(),
    }
    return config if all(config.values()) else None


def _doc_to_dto(d: RagDocument) -> DocumentDTO:
    return DocumentDTO(
        id=d.id,
        kb_id=d.kb_id,
        file_name=d.file_name,
        file_url=d.file_url,
        file_type=d.file_type,
        file_size=d.file_size,
        chunk_count=d.chunk_count,
        parse_status=d.parse_status,
        error_message=d.error_message,
        created_time=str(d.created_time) if d.created_time else None,
        updated_time=str(d.updated_time) if d.updated_time else None,
    )


def _chunk_to_dto(c: RagChunk) -> ChunkDTO:
    return ChunkDTO(
        id=c.id,
        kb_id=c.kb_id,
        doc_id=c.doc_id,
        chunk_index=c.chunk_index,
        content=c.content,
        token_count=c.token_count,
        created_time=str(c.created_time) if c.created_time else None,
    )


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _get_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


async def _index_document_content(
    db: AsyncSession,
    kb: RagKnowledgeBase,
    doc: RagDocument,
    content: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> int:
    """对文本内容切片并向量化，写入 rag_chunk。返回 chunk 数。"""
    if not _RAG_SERVICE_AVAILABLE:
        raise RuntimeError("rag_service 不可用，无法生成向量")
    if not content or not content.strip():
        raise RuntimeError("文档内容为空")

    chunks = _split_text(content, chunk_size=chunk_size, overlap=chunk_overlap)
    if not chunks:
        raise RuntimeError("切片结果为空")

    # 先清理旧 chunks（reindex 场景）
    await db.execute(
        delete(RagChunk).where(RagChunk.doc_id == doc.id)
    )

    total = 0
    runtime_config = _knowledge_base_embedding_runtime_config(kb)
    for idx, chunk_text in enumerate(chunks):
        try:
            embedding = await _generate_embedding(
                chunk_text,
                runtime_config=runtime_config,
            )
        except Exception as exc:
            logger.warning(
                "chunk 向量化失败 index=%d errorType=%s",
                idx,
                type(exc).__name__,
            )
            continue
        if not embedding:
            continue
        c = RagChunk(
            kb_id=kb.id,
            doc_id=doc.id,
            chunk_index=idx,
            content=chunk_text,
            embedding=json.dumps(embedding, ensure_ascii=False),
            token_count=len(chunk_text),
        )
        db.add(c)
        total += 1

    doc.chunk_count = total
    doc.parse_status = "ready" if total > 0 else "failed"
    if total == 0:
        doc.error_message = "所有切片向量化均失败"
    await db.commit()
    return total


async def _refresh_kb_counts(db: AsyncSession, kb_id: int) -> None:
    doc_count = (await db.execute(
        select(func.count()).select_from(
            select(RagDocument).where(
                RagDocument.kb_id == kb_id,
                RagDocument.deleted == 0,
            ).subquery()
        )
    )).scalar() or 0
    chunk_count = (await db.execute(
        select(func.count()).select_from(
            select(RagChunk).where(RagChunk.kb_id == kb_id).subquery()
        )
    )).scalar() or 0
    kb = (await db.execute(
        select(RagKnowledgeBase).where(RagKnowledgeBase.id == kb_id)
    )).scalar_one_or_none()
    if kb:
        kb.doc_count = doc_count
        kb.chunk_count = chunk_count
        await db.commit()


# ============================================================
# 知识库 CRUD
# ============================================================
@router.get("/knowledge-bases", response_model=ResultObject[List[KnowledgeBaseDTO]])
async def list_knowledge_bases(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        stmt = select(RagKnowledgeBase).where(
            RagKnowledgeBase.deleted == 0
        ).order_by(RagKnowledgeBase.id.desc())
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return ResultObject.success([_kb_to_dto(kb) for kb in rows])
    except Exception as e:
        logger.error("列出知识库失败", exc_info=True)
        return ResultObject.internal_error()


@router.post("/knowledge-bases", response_model=ResultObject[KnowledgeBaseDTO])
async def create_knowledge_base(
    req: KnowledgeBaseUpsertDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    embedding_base_url = await _validated_embedding_base_url(req.embedding_base_url)
    try:
        kb = RagKnowledgeBase(
            name=req.name,
            description=req.description,
            embedding_model=req.embedding_model,
            embedding_api_key=prepare_secret_for_storage(
                incoming=req.embedding_api_key,
                purpose=RAG_EMBEDDING_API_KEY_PURPOSE,
                clear=req.clear_embedding_api_key,
            ),
            embedding_base_url=embedding_base_url,
            status=req.status if req.status is not None else 1,
        )
        db.add(kb)
        await db.commit()
        await db.refresh(kb)
        return ResultObject.success(_kb_to_dto(kb))
    except Exception as e:
        logger.error("新建知识库失败", exc_info=True)
        return ResultObject.internal_error()


@router.get("/knowledge-bases/{kb_id}", response_model=ResultObject[KnowledgeBaseDTO])
async def get_knowledge_base(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        result = await db.execute(
            select(RagKnowledgeBase).where(
                RagKnowledgeBase.id == kb_id,
                RagKnowledgeBase.deleted == 0,
            )
        )
        kb = result.scalar_one_or_none()
        if not kb:
            return ResultObject.failed("知识库不存在")
        return ResultObject.success(_kb_to_dto(kb))
    except Exception as e:
        logger.error("获取知识库失败 id=%s", kb_id, exc_info=True)
        return ResultObject.internal_error()


@router.put("/knowledge-bases/{kb_id}", response_model=ResultObject[KnowledgeBaseDTO])
async def update_knowledge_base(
    kb_id: int,
    req: KnowledgeBaseUpsertDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    embedding_base_url = (
        await _validated_embedding_base_url(req.embedding_base_url)
        if req.embedding_base_url is not None
        else None
    )
    try:
        result = await db.execute(
            select(RagKnowledgeBase).where(
                RagKnowledgeBase.id == kb_id,
                RagKnowledgeBase.deleted == 0,
            )
        )
        kb = result.scalar_one_or_none()
        if not kb:
            return ResultObject.failed("知识库不存在")
        kb.name = req.name
        if req.description is not None:
            kb.description = req.description
        if req.embedding_model is not None:
            kb.embedding_model = req.embedding_model
        incoming_api_key = str(req.embedding_api_key or "").strip()
        if (
            req.embedding_base_url is not None
            and _embedding_origin(kb.embedding_base_url) != _embedding_origin(embedding_base_url)
            and bool(str(kb.embedding_api_key or "").strip())
            and not incoming_api_key
            and not req.clear_embedding_api_key
        ):
            return ResultObject.validate_failed(
                "向量服务地址已变更；为防止把已保存密钥发送到新主机，请重新输入 API Key 或明确清除旧密钥"
            )
        kb.embedding_api_key = prepare_secret_for_storage(
            incoming=req.embedding_api_key,
            existing=kb.embedding_api_key,
            purpose=RAG_EMBEDDING_API_KEY_PURPOSE,
            clear=req.clear_embedding_api_key,
        )
        if req.embedding_base_url is not None:
            kb.embedding_base_url = embedding_base_url
        if req.status is not None:
            kb.status = req.status
        await db.commit()
        await db.refresh(kb)
        return ResultObject.success(_kb_to_dto(kb))
    except Exception as e:
        logger.error("更新知识库失败 id=%s", kb_id, exc_info=True)
        return ResultObject.internal_error()


@router.delete("/knowledge-bases/{kb_id}", response_model=ResultObject[str])
async def delete_knowledge_base(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        result = await db.execute(
            select(RagKnowledgeBase).where(
                RagKnowledgeBase.id == kb_id,
                RagKnowledgeBase.deleted == 0,
            )
        )
        kb = result.scalar_one_or_none()
        if not kb:
            return ResultObject.failed("知识库不存在")
        kb.deleted = 1
        # 软删所有文档
        docs_result = await db.execute(
            select(RagDocument).where(
                RagDocument.kb_id == kb_id,
                RagDocument.deleted == 0,
            )
        )
        for d in docs_result.scalars().all():
            d.deleted = 1
        # 物理删除所有 chunks
        await db.execute(delete(RagChunk).where(RagChunk.kb_id == kb_id))
        await db.commit()
        return ResultObject.success("删除成功")
    except Exception as e:
        logger.error("删除知识库失败 id=%s", kb_id, exc_info=True)
        return ResultObject.internal_error()


# ============================================================
# 文档管理
# ============================================================
@router.get("/knowledge-bases/{kb_id}/documents", response_model=ResultObject[List[DocumentDTO]])
async def list_documents(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        result = await db.execute(
            select(RagDocument).where(
                RagDocument.kb_id == kb_id,
                RagDocument.deleted == 0,
            ).order_by(RagDocument.id.desc())
        )
        rows = result.scalars().all()
        return ResultObject.success([_doc_to_dto(d) for d in rows])
    except Exception as e:
        logger.error("列出文档失败 kb=%s", kb_id, exc_info=True)
        return ResultObject.internal_error()


@router.post("/knowledge-bases/{kb_id}/documents", response_model=ResultObject[DocumentDTO])
async def upload_document(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    file: Optional[UploadFile] = File(None),
    content: Optional[str] = Form(None),
    file_name: Optional[str] = Form(None),
):
    """上传文档（文件上传或文本输入二选一）。

    - 文件上传：支持 .txt / .md，自动 decode
    - 文本输入：直接作为正文，file_name 由调用方提供
    """
    try:
        kb_result = await db.execute(
            select(RagKnowledgeBase).where(
                RagKnowledgeBase.id == kb_id,
                RagKnowledgeBase.deleted == 0,
            )
        )
        kb = kb_result.scalar_one_or_none()
        if not kb:
            return ResultObject.failed("知识库不存在")

        text_content = ""
        actual_name = file_name or ""
        file_type = None
        file_size = 0

        if file is not None:
            actual_name = _safe_document_name(file.filename, fallback="upload.txt")
            ext = _get_extension(actual_name)
            if ext not in ALLOWED_TEXT_EXTS:
                raise HTTPException(
                    status_code=415,
                    detail="仅支持 UTF-8 编码的 .txt、.md 或 .markdown 文档",
                )
            file_type = ext.lstrip(".") or "txt"
            try:
                raw = await read_upload_limited(file, MAX_UPLOAD_SIZE)
            except UploadValidationError as exc:
                raise HTTPException(status_code=413, detail=str(exc)) from exc
            file_size = len(raw)
            try:
                text_content = raw.decode("utf-8-sig", errors="strict")
            except UnicodeDecodeError as exc:
                raise HTTPException(status_code=415, detail="文档必须使用 UTF-8 编码") from exc
        elif content:
            text_content = content
            try:
                file_size = len(content.encode("utf-8"))
            except UnicodeEncodeError as exc:
                raise HTTPException(status_code=422, detail="文本包含无效 Unicode 字符") from exc
            if file_size > MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"文档不能超过 {MAX_UPLOAD_SIZE // 1024 // 1024}MB",
                )
            if not actual_name:
                actual_name = f"manual-{uuid.uuid4().hex[:8]}.txt"
            actual_name = _safe_document_name(actual_name, fallback="manual.txt")
            if _get_extension(actual_name) not in ALLOWED_TEXT_EXTS:
                raise HTTPException(status_code=415, detail="文本内容的文件名必须使用 .txt 或 .md 扩展名")
            file_type = _get_extension(actual_name).lstrip(".") or "txt"
        else:
            return ResultObject.validate_failed("必须提供 file 或 content")

        if not text_content.strip():
            raise HTTPException(status_code=422, detail="文档内容不能为空")
        if "\x00" in text_content:
            raise HTTPException(status_code=415, detail="文档包含不支持的二进制内容")

        doc = RagDocument(
            kb_id=kb_id,
            file_name=actual_name,
            file_type=file_type,
            file_size=file_size,
            parse_status="pending",
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        # 索引
        if text_content.strip():
            try:
                await _index_document_content(db, kb, doc, text_content)
            except Exception as ie:
                doc.parse_status = "failed"
                doc.error_message = str(ie)
                await db.commit()
                logger.warning("文档索引失败 doc=%s: %s", doc.id, ie)
        await _refresh_kb_counts(db, kb_id)
        # 重新刷新 doc
        await db.refresh(doc)
        return ResultObject.success(_doc_to_dto(doc))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("上传文档失败 kb=%s", kb_id, exc_info=True)
        return ResultObject.failed("上传文档失败，请稍后重试")
    finally:
        if file is not None:
            await file.close()


@router.delete(
    "/knowledge-bases/{kb_id}/documents/{doc_id}",
    response_model=ResultObject[str],
)
async def delete_document(
    kb_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        result = await db.execute(
            select(RagDocument).where(
                RagDocument.id == doc_id,
                RagDocument.kb_id == kb_id,
                RagDocument.deleted == 0,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return ResultObject.failed("文档不存在")
        doc.deleted = 1
        await db.execute(delete(RagChunk).where(RagChunk.doc_id == doc_id))
        await db.commit()
        await _refresh_kb_counts(db, kb_id)
        return ResultObject.success("删除成功")
    except Exception as e:
        logger.error("删除文档失败 doc=%s", doc_id, exc_info=True)
        return ResultObject.internal_error()


@router.post(
    "/knowledge-bases/{kb_id}/documents/{doc_id}/reindex",
    response_model=ResultObject[DocumentDTO],
)
async def reindex_document(
    kb_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """重新索引文档（需要文档存在 content 字段；当前简化版仅清理 chunks，不重新解析原文件）。"""
    try:
        result = await db.execute(
            select(RagDocument).where(
                RagDocument.id == doc_id,
                RagDocument.kb_id == kb_id,
                RagDocument.deleted == 0,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return ResultObject.failed("文档不存在")

        # 简化版：从现有 chunks 拼接 content 重新索引
        chunks_result = await db.execute(
            select(RagChunk).where(RagChunk.doc_id == doc_id).order_by(RagChunk.chunk_index)
        )
        existing = chunks_result.scalars().all()
        if not existing:
            return ResultObject.failed("文档无可重新索引的内容（原始内容未持久化）")

        content = "\n\n".join((c.content or "") for c in existing)
        kb_result = await db.execute(
            select(RagKnowledgeBase).where(RagKnowledgeBase.id == kb_id)
        )
        kb = kb_result.scalar_one_or_none()
        if not kb:
            return ResultObject.failed("知识库不存在")

        count = await _index_document_content(db, kb, doc, content)
        await _refresh_kb_counts(db, kb_id)
        await db.refresh(doc)
        return ResultObject.success(_doc_to_dto(doc))
    except Exception as e:
        logger.error("重新索引文档失败 doc=%s", doc_id, exc_info=True)
        return ResultObject.internal_error()


@router.get(
    "/knowledge-bases/{kb_id}/documents/{doc_id}/chunks",
    response_model=ResultObject[List[ChunkDTO]],
)
async def list_chunks(
    kb_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        result = await db.execute(
            select(RagChunk).where(
                RagChunk.kb_id == kb_id,
                RagChunk.doc_id == doc_id,
            ).order_by(RagChunk.chunk_index)
        )
        rows = result.scalars().all()
        return ResultObject.success([_chunk_to_dto(c) for c in rows])
    except Exception as e:
        logger.error("列出 chunks 失败 doc=%s", doc_id, exc_info=True)
        return ResultObject.internal_error()


# ============================================================
# 检索与对话
# ============================================================
@router.post("/knowledge-bases/{kb_id}/search", response_model=ResultObject[List[SearchHitDTO]])
async def search_knowledge_base(
    kb_id: int,
    req: SearchReqDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """向量检索：在指定知识库内检索 top_k 相关分块。"""
    try:
        if not _RAG_SERVICE_AVAILABLE:
            return ResultObject.failed("rag_service 不可用，无法生成查询向量")
        if not req.query or not req.query.strip():
            return ResultObject.validate_failed("query 不能为空")

        try:
            query_emb = await _generate_embedding(req.query)
        except Exception as e:
            return ResultObject.internal_error()
        if not query_emb:
            return ResultObject.failed("查询向量化返回空")

        result = await db.execute(
            select(RagChunk).where(RagChunk.kb_id == kb_id)
        )
        chunks = result.scalars().all()

        hits: List[SearchHitDTO] = []
        threshold = req.similarity_threshold if req.similarity_threshold is not None else DEFAULT_SIMILARITY_THRESHOLD
        for c in chunks:
            try:
                emb = json.loads(c.embedding) if c.embedding else []
            except (ValueError, TypeError):
                continue
            score = _cosine_similarity(query_emb, emb)
            if score >= threshold:
                hits.append(SearchHitDTO(
                    chunk_id=c.id,
                    doc_id=c.doc_id,
                    content=c.content,
                    score=round(score, 4),
                ))
        hits.sort(key=lambda h: h.score or 0, reverse=True)
        top_k = req.top_k or DEFAULT_TOP_K
        return ResultObject.success(hits[:top_k])
    except Exception as e:
        logger.error("知识库检索失败 kb=%s", kb_id, exc_info=True)
        return ResultObject.internal_error()


@router.post("/chat", response_model=ResultObject[ChatRespDTO])
async def rag_chat(
    req: ChatReqDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """RAG 增强对话：跨多个知识库检索后调用 AI 生成回复。"""
    try:
        if not _RAG_SERVICE_AVAILABLE:
            return ResultObject.failed("rag_service 不可用")
        if not _AI_AVAILABLE:
            return ResultObject.failed("ai_provider 不可用")
        if not req.query or not req.query.strip():
            return ResultObject.validate_failed("query 不能为空")

        # 生成查询向量
        try:
            query_emb = await _generate_embedding(req.query)
        except Exception as e:
            return ResultObject.internal_error()
        if not query_emb:
            return ResultObject.failed("查询向量化返回空")

        # 跨知识库检索
        kb_ids = req.knowledge_base_ids or []
        stmt = select(RagChunk)
        if kb_ids:
            stmt = stmt.where(RagChunk.kb_id.in_(kb_ids))
        result = await db.execute(stmt)
        chunks = result.scalars().all()

        hits: List[SearchHitDTO] = []
        threshold = req.similarity_threshold if req.similarity_threshold is not None else DEFAULT_SIMILARITY_THRESHOLD
        for c in chunks:
            try:
                emb = json.loads(c.embedding) if c.embedding else []
            except (ValueError, TypeError):
                continue
            score = _cosine_similarity(query_emb, emb)
            if score >= threshold:
                hits.append(SearchHitDTO(
                    chunk_id=c.id,
                    doc_id=c.doc_id,
                    content=c.content,
                    score=round(score, 4),
                ))
        hits.sort(key=lambda h: h.score or 0, reverse=True)
        top_k = req.top_k or DEFAULT_TOP_K
        hits = hits[:top_k]

        # 构造 prompt
        context = "\n---\n".join((h.content or "") for h in hits if h.content)
        system_prompt = req.system_prompt or (
            "你是闲鱼客服回复助手。请根据提供的参考资料回答用户问题。"
            "如果参考资料中没有相关信息，请明确告知用户并礼貌地提供帮助。"
            "回答要简洁、专业、礼貌，避免编造信息。"
        )
        user_message = (
            f"参考资料：\n{context}\n\n"
            f"用户问题：{req.query}\n\n"
            "请根据参考资料回答问题。"
        ) if context else f"用户问题：{req.query}\n\n请回答用户的问题。"

        try:
            ai_result = await _ai_generate_text(
                scene="rag_chat",
                system_prompt=system_prompt,
                user_prompt=user_message,
                temperature=0.3,
            )
        except Exception as e:
            return ResultObject.internal_error()

        if not ai_result.get("ok"):
            return ResultObject.failed(ai_result.get("error") or "AI 生成失败")

        answer = ai_result.get("content") or ""
        return ResultObject.success(ChatRespDTO(
            answer=answer,
            hits=hits,
            hit_count=len(hits),
        ))
    except Exception as e:
        logger.error("RAG 对话失败", exc_info=True)
        return ResultObject.internal_error()
