from pydantic import BaseModel, ConfigDict


class BaseRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
