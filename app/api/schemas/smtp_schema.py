from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, model_validator

from app.api.schemas.base_schema import BaseRequest

SmtpEncryption = Literal["none", "starttls", "tls"]


class SmtpUpdate(BaseRequest):
    model_config = ConfigDict(str_strip_whitespace=False)

    version: int = Field(ge=1)
    host: str = Field(max_length=253, pattern=r"^[^\s/\\@]*$")
    port: int = Field(ge=1, le=65535)
    encryption: SmtpEncryption
    username: str = Field(default="", max_length=320)
    sender: EmailStr | Literal[""]
    password: SecretStr = Field(default=SecretStr(""), max_length=4096)

    @model_validator(mode="after")
    def require_complete_server(self):
        if bool(self.host) != bool(self.sender):
            raise ValueError("SMTP server and sender must be configured together.")
        return self


class SmtpStatus(BaseModel):
    version: int
    host: str
    port: int
    encryption: SmtpEncryption
    username: str
    sender: str
    has_password: bool
    status: Literal["not_configured", "untested", "tested"]
    account_mail_hint: str | None = None


class SmtpTestRequest(BaseRequest):
    recipient: EmailStr
    settings: SmtpUpdate | None = None
