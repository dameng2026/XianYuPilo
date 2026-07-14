import logging

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from .config import settings

logger = logging.getLogger(__name__)

def create_configured_engine(database_url):
    """Create an engine without ever rendering its credential-bearing URL."""

    return create_async_engine(
        database_url,
        echo=False,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": settings.mysql_connect_timeout_seconds,
            # aiomysql does not expose client-side socket read/write timeout
            # arguments. Configure the equivalent MySQL session safeguards on
            # every new connection instead.
            "init_command": (
                "SET SESSION net_read_timeout="
                f"{settings.mysql_read_timeout_seconds}, "
                "SESSION net_write_timeout="
                f"{settings.mysql_write_timeout_seconds}"
            ),
        },
    )


DATABASE_URL = settings.mysql_runtime_url
engine = create_configured_engine(DATABASE_URL)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        except BaseException:
            try:
                await session.rollback()
            except Exception:
                logger.warning("Database rollback failed", exc_info=True)
            raise
        finally:
            await session.close()
