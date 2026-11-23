from datetime import datetime
from typing import ClassVar

from sqlalchemy import CheckConstraint, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import Base


class SmtpSettings(Base):
    __tablename__ = "smtp_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_smtp_settings_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    host: Mapped[str]
    port: Mapped[int]
    encryption: Mapped[str]
    username: Mapped[str]
    sender: Mapped[str]
    encrypted_password: Mapped[str | None] = mapped_column(Text)
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column()

    __mapper_args__: ClassVar[dict[str, object]] = {"version_id_col": version}
