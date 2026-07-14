from ..core.camel import CamelModel


class ChangePasswordReqDTO(CamelModel):
    old_password: str
    new_password: str
