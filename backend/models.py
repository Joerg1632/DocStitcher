from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base  # импортируем общий Base из database.py

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

    licenses = relationship("License", back_populates="user")

class License(Base):
    __tablename__ = 'licenses'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    license_key = Column(String, unique=True)
    allowed_devices = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="licenses")
    devices = relationship("LicenseDevice", back_populates="license")

class LicenseDevice(Base):
    __tablename__ = 'license_devices'

    id = Column(Integer, primary_key=True)
    license_id = Column(Integer, ForeignKey('licenses.id'), nullable=False)
    device_id = Column(String, nullable=False)
    activated_at = Column(DateTime, default=datetime.utcnow)

    license = relationship("License", back_populates="devices")
