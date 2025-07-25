import sqlalchemy
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.database import Base

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)

    licenses = relationship("License", back_populates="user")

class LicenseType(Base):
    __tablename__ = "license_types"

    code = Column(String(50), primary_key=True)  # 'LICENSE-TRIAL', 'LICENSE-1', 'LICENSE-5', 'LICENSE-15', 'LICENSE-UNLIMITED'
    allowed_devices = Column(Integer, nullable=True)  # None = без ограничений
    expires_days = Column(Integer, nullable=True)     # None = бессрочно

    licenses = relationship("License", back_populates="license_type")

class License(Base):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    license_type_code = Column(String(50), ForeignKey("license_types.code"), nullable=False)
    license_key = Column(String(36), unique=True, nullable=False)  # UUID
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        sqlalchemy.UniqueConstraint("user_id", "license_type_code", name="uq_user_license_type"),
    )

    user = relationship("User", back_populates="licenses")
    license_type = relationship("LicenseType", back_populates="licenses")
    devices = relationship("LicenseDevice", back_populates="license")

class LicenseDevice(Base):
    __tablename__ = 'license_devices'

    id = Column(Integer, primary_key=True)
    license_id = Column(Integer, ForeignKey('licenses.id'), nullable=False)
    device_id = Column(String(36), nullable=False)  # UUID устройства
    activated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    license = relationship("License", back_populates="devices")

    __table_args__ = (
        sqlalchemy.Index('idx_license_device', 'license_id', 'device_id', unique=True),
    )