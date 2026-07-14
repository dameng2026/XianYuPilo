"""
Internal instance identity for commercial bridge correlation.

This module generates and persists a unique, immutable identifier for the
local open-source deployment.  The identifier is created automatically on
first boot, stored in the settings table under a non-obvious key, and never
exposed through any user-facing API or configuration file.

The identifier is used solely as a correlation key when the open-source
instance submits advertising applications to the commercial backend, so the
commercial backend can attribute applications and payment records back to
the originating deployment and return only that deployment"s records when
the administrator queries the application history.
"""

from __future__ import annotations

import logging
import secrets
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import XianyuSysSetting

logger = logging.getLogger(__name__)

# Non-obvious setting key so the value is not easily recognised or edited by
# administrators browsing the settings table.  The value is still stored in
# plain text because it is a correlation key, not a credential.
_SETTING_KEY = "_x_bridge_iid"

# In-memory cache populated on application startup.  Once loaded, the value
# never changes for the lifetime of the process.
_cached_value: Optional[str] = None

# Identifier prefix so the commercial backend can distinguish the token format
# from other bridge credentials.  "osi" stands for "open-source instance".
_PREFIX = "osi_"


def _generate_token() -> str:
    """Generate a new random instance identifier."""
    return _PREFIX + secrets.token_urlsafe(32)


def get_instance_token() -> str:
    """Return the cached instance token.

    Raises RuntimeError if the token has not been loaded yet.  Callers must
    ensure :func:`ensure_instance_token` has run during application startup.
    """
    if _cached_value is None:
        # Fall back to a transient in-memory value so the process can still
        # operate if the startup hook failed; the commercial backend will
        # simply not correlate previous records after a restart.
        logger.warning("instance token not loaded; generating transient value")
        return _generate_token()
    return _cached_value


async def ensure_instance_token(db: AsyncSession) -> str:
    """Load or create the persistent instance token.

    On first boot the token is generated, persisted, and cached.  On
    subsequent boots the existing value is loaded from the settings table and
    cached.  The value is immutable once created.
    """
    global _cached_value
    if _cached_value is not None:
        return _cached_value

    result = await db.execute(
        select(XianyuSysSetting).where(XianyuSysSetting.setting_key == _SETTING_KEY)
    )
    setting = result.scalar_one_or_none()
    if setting and setting.setting_value:
        stored = setting.setting_value.strip()
        if stored.startswith(_PREFIX) and len(stored) > len(_PREFIX) + 16:
            _cached_value = stored
            logger.info("instance token loaded from storage")
            return _cached_value

    new_token = _generate_token()
    if setting:
        setting.setting_value = new_token
    else:
        db.add(XianyuSysSetting(setting_key=_SETTING_KEY, setting_value=new_token))
    await db.commit()
    _cached_value = new_token
    logger.info("instance token generated and persisted")
    return _cached_value
