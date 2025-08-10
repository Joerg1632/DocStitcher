import sqlalchemy
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime, timezone

Base = declarative_base()

class LicenseType(Base):
    __tablename__ = "license_types"

    code = Column(String(50), primary_key=True)    # 'LICENSE-TRIAL', 'LICENSE-UNLIMITED', 'LICENSE-1-MONTH',
    # 'LICENSE-5-MONTH', 'LICENSE-15-MONTH', 'LICENSE-1-YEAR', 'LICENSE-5-YEAR', 'LICENSE-15-YEAR'
    allowed_devices = Column(Integer, nullable=True)
    expires_days = Column(Integer, nullable=True)

    licenses = relationship("License", back_populates="license_type")

class License(Base):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True)
    license_type_code = Column(String(50), ForeignKey("license_types.code"), nullable=False)
    license_key = Column(String(36), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)

    license_type = relationship("LicenseType", back_populates="licenses")
    devices = relationship("LicenseDevice", back_populates="license")

class LicenseDevice(Base):
    __tablename__ = 'license_devices'

    id = Column(Integer, primary_key=True)
    license_id = Column(Integer, ForeignKey('licenses.id'), nullable=False)
    device_id = Column(String(36), nullable=False)
    activated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    license = relationship("License", back_populates="devices")

    __table_args__ = (
        sqlalchemy.Index('idx_license_device', 'license_id', 'device_id', unique=True),
    )