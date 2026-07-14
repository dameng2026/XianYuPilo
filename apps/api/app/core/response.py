from typing import Any, Optional, Generic, TypeVar
from pydantic import BaseModel
from .camel import CamelModel
from .logging_security import redact_sensitive_text

T = TypeVar("T")


class ResultObject(CamelModel, Generic[T]):
    code: int = 200
    msg: str = "操作成功"
    data: Optional[T] = None

    @staticmethod
    def success(data: Any = None, message: str = "操作成功") -> "ResultObject":
        return ResultObject(code=200, msg=message, data=data)

    @staticmethod
    def failed(message: str = "操作失败", code: int = 500) -> "ResultObject":
        return ResultObject(code=code, msg=redact_sensitive_text(message), data=None)

    @staticmethod
    def internal_error(
        public_message: str = "服务器内部错误，请稍后重试",
        exc: BaseException | None = None,
        request_id: str | None = None,
    ) -> "ResultObject":
        """Return a stable public error without serialising internal exceptions."""
        del exc  # Exceptions belong in redacted server logs, never API payloads.
        data = {"requestId": request_id} if request_id else None
        return ResultObject(
            code=500,
            msg=redact_sensitive_text(public_message),
            data=data,
        )

    @staticmethod
    def validate_failed(message: str = "参数验证失败") -> "ResultObject":
        return ResultObject(code=400, msg=redact_sensitive_text(message), data=None)

    @staticmethod
    def unauthorized(data: Any = None) -> "ResultObject":
        return ResultObject(code=401, msg="暂未登录或token已经过期", data=data)

    @staticmethod
    def forbidden(data: Any = None) -> "ResultObject":
        return ResultObject(code=403, msg="没有相关权限", data=data)
