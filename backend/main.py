from fastapi import FastAPI, HTTPException, Depends
from fastapi.params import Security
from pydantic import BaseModel
from database import SessionLocal
import models
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import jwt
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
import os

app = FastAPI()

security = HTTPBearer()

# Настройки JWT (сделаем временно простым секретом)
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 дней

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class LicenseActivateRequest(BaseModel):
    license_key: str
    device_id: str

class LicenseActivateResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # payload должен содержать license_key, device_id, user_id
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Токен истек")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Неверный токен")

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@app.post("/activate", response_model=LicenseActivateResponse)
def activate_license(request: LicenseActivateRequest, db: Session = Depends(get_db)):
    # Поиск лицензии по ключу
    license = db.query(models.License).filter(models.License.license_key == request.license_key).first()
    if not license:
        raise HTTPException(status_code=404, detail="Лицензия не найдена")

    # Проверка срока действия лицензии
    if license.expires_at and license.expires_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Лицензия истекла")

    # Проверяем сколько устройств уже активировано
    activated_devices_count = db.query(models.LicenseDevice).filter(models.LicenseDevice.license_id == license.id).count()

    # Если лицензия не безлимитная и устройство не зарегистрировано — проверяем лимит
    existing_device = db.query(models.LicenseDevice).filter(
        models.LicenseDevice.license_id == license.id,
        models.LicenseDevice.device_id == request.device_id
    ).first()

    if not existing_device:
        if license.allowed_devices is not None and activated_devices_count >= license.allowed_devices:
            raise HTTPException(status_code=403, detail="Превышено максимальное число устройств")
        # Добавляем устройство
        new_device = models.LicenseDevice(
            license_id=license.id,
            device_id=request.device_id,
            activated_at=datetime.utcnow()
        )
        db.add(new_device)
        db.commit()

    # Создаем JWT токен
    token_data = {
        "license_key": license.license_key,
        "device_id": request.device_id,
        "user_id": license.user_id
    }
    access_token = create_access_token(token_data, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return LicenseActivateResponse(access_token=access_token)


@app.get("/verify")
def verify(credentials: HTTPAuthorizationCredentials = Security(security), db: Session = Depends(get_db)):
    payload = verify_token(credentials.credentials)

    license_key = payload.get("license_key")
    device_id = payload.get("device_id")

    license = db.query(models.License).filter(models.License.license_key == license_key).first()
    if not license:
        raise HTTPException(status_code=404, detail="Лицензия не найдена")

    # Проверяем срок действия лицензии
    if license.expires_at and license.expires_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Лицензия истекла")

    # Проверяем, что устройство активировано
    device = db.query(models.LicenseDevice).filter(
        models.LicenseDevice.license_id == license.id,
        models.LicenseDevice.device_id == device_id
    ).first()

    if not device:
        raise HTTPException(status_code=403, detail="Устройство не активировано")

    return {"status": "ok", "message": "Лицензия и устройство валидны"}
