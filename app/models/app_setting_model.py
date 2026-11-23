from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]
