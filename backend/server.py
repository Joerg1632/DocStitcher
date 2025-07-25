from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from backend.database import SessionLocal
from backend import models
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import jwt
import os
from dotenv import load_dotenv

from backend.models import LicenseDevice, LicenseType, License

app = FastAPI()
security = HTTPBearer()

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY не установлен в переменных окружения")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 дней

# ------------------------ Pydantic модели ------------------------

class UserCreate(BaseModel):
    username: str
    email: str

class LicenseCreate(BaseModel):
    user_id: int | None = None
    license_type_code: str
    license_key: str

class LicenseAssignRequest(BaseModel):
    user_id: int
    license_key: str

class LicenseChangeRequest(BaseModel):
    user_id: int
    new_license_key: str

class LicenseActivateRequest(BaseModel):
    license_key: str
    device_id: str

class LicenseActivateResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LicenseTypeCreate(BaseModel):
    code: str
    allowed_devices: int | None = None
    expires_days: int | None = None

class TrialActivateRequest(BaseModel):
    device_id: str
# ------------------------ Вспомогательные функции ------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Токен истек")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Неверный токен")

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def check_license_expiration(license: models.License, db: Session):
    now = datetime.now(timezone.utc)
    expires_days = license.license_type.expires_days
    if expires_days is not None:
        expiration_date = license.created_at + timedelta(days=expires_days)
        if expiration_date < now:
            license.is_active = False
            db.commit()
            raise HTTPException(status_code=403, detail="Лицензия истекла")

# ------------------------ Эндпоинты ------------------------
@app.post("/activate_trial")
def activate_trial(data: dict, db: Session = Depends(get_db)):
    device_id = data.get("device_id")
    # Проверяем, не активирована ли пробная лицензия для этого устройства
    existing_device = db.query(LicenseDevice).join(License).filter(
        LicenseDevice.device_id == device_id,
        License.license_type_code == "LICENSE-TRIAL"
    ).first()
    if existing_device:
        raise HTTPException(status_code=403, detail="Пробная версия уже активирована на этом устройстве")

    # Создаём новую пробную лицензию
    license_type = db.query(LicenseType).filter(LicenseType.code == "LICENSE-TRIAL").first()
    if not license_type:
        raise HTTPException(status_code=404, detail="Тип лицензии не найден")

    license = License(
        license_type_code="LICENSE-TRIAL",
        created_at=datetime.now(timezone.utc),
        is_active=True
    )
    db.add(license)
    db.commit()
    db.refresh(license)

    # Привязываем устройство
    license_device = LicenseDevice(
        license_id=license.id,
        device_id=device_id
    )
    db.add(license_device)
    db.commit()

    # Генерируем JWT-токен
    from jwt import encode
    token = encode({"license_id": license.id, "device_id": device_id}, SECRET_KEY, algorithm="HS256")
    return {"access_token": token}

@app.get("/license/{license_id}")
def get_license(license_id: int, credentials: HTTPAuthorizationCredentials = Security(security), db: Session = Depends(get_db)):
    payload = verify_token(credentials.credentials)
    license = db.query(models.License).filter(models.License.id == license_id).first()
    if not license:
        raise HTTPException(status_code=404, detail="Лицензия не найдена")
    check_license_expiration(license, db)
    return {
        "license_id": license.id,
        "license_type_code": license.license_type_code,
        "created_at": license.created_at.isoformat(),
        "is_active": license.is_active,
        "expires_days": license.license_type.expires_days
    }

@app.get("/license_types")
def get_license_types(db: Session = Depends(get_db)):
    license_types = db.query(models.LicenseType).filter(models.LicenseType.code != "LICENSE-TRIAL").all()
    return [{"code": lt.code} for lt in license_types]

@app.post("/create_license")
def create_license(data: LicenseCreate, db: Session = Depends(get_db)):
    # Создаём нового пользователя автоматически, если user_id не указан
    if data.user_id is None:
        user = models.User()
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    else:
        user = db.query(models.User).filter(models.User.id == data.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        user_id = data.user_id

    license_type = db.query(models.LicenseType).filter(models.LicenseType.code == data.license_type_code).first()
    if not license_type:
        raise HTTPException(status_code=404, detail="Тип лицензии не найден")

    existing_license = db.query(models.License).filter(models.License.license_key == data.license_key).first()
    if existing_license:
        raise HTTPException(status_code=400, detail="Лицензия с таким ключом уже существует")

    license = models.License(
        user_id=user_id,
        license_type_code=data.license_type_code,
        license_key=data.license_key,
        created_at=datetime.now(timezone.utc),
        is_active=True
    )
    db.add(license)
    db.commit()
    db.refresh(license)
    return {"license_key": license.license_key, "user_id": user_id}
@app.post("/create_license_type")
def create_license_type(data: LicenseTypeCreate, db: Session = Depends(get_db)):
    existing = db.query(models.LicenseType).filter(models.LicenseType.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Тип лицензии уже существует")
    license_type = models.LicenseType(
        code=data.code,
        allowed_devices=data.allowed_devices,
        expires_days=data.expires_days
    )
    db.add(license_type)
    db.commit()
    return {"message": "Тип лицензии создан"}

@app.post("/change_license")
def change_license(data: LicenseChangeRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    old_license = db.query(models.License).filter(
        models.License.user_id == data.user_id,
        models.License.is_active == True
    ).first()
    if not old_license:
        raise HTTPException(status_code=404, detail="У пользователя нет активной лицензии")

    new_license = db.query(models.License).filter(models.License.license_key == data.new_license_key).first()
    if not new_license:
        raise HTTPException(status_code=404, detail="Новая лицензия не найдена")

    if new_license.user_id is not None and new_license.user_id != data.user_id:
        raise HTTPException(status_code=400, detail="Новая лицензия уже назначена другому пользователю")

    check_license_expiration(old_license, db)

    devices = db.query(models.LicenseDevice).filter(models.LicenseDevice.license_id == old_license.id).all()
    for device in devices:
        existing = db.query(models.LicenseDevice).filter(
            models.LicenseDevice.license_id == new_license.id,
            models.LicenseDevice.device_id == device.device_id
        ).first()
        if not existing:
            device.license_id = new_license.id
        else:
            db.delete(device)

    old_license.is_active = False
    new_license.user_id = data.user_id
    new_license.is_active = True
    db.commit()
    return {"message": "Лицензия изменена, устройства перенесены"}

@app.post("/activate", response_model=LicenseActivateResponse)
def activate_license(request: LicenseActivateRequest, db: Session = Depends(get_db)):
    license = db.query(models.License).filter(models.License.license_key == request.license_key).first()
    if not license:
        raise HTTPException(status_code=404, detail="Лицензия не найдена")

    if not license.is_active:
        raise HTTPException(status_code=403, detail="Лицензия не активна")

    check_license_expiration(license, db)

    existing_device = db.query(models.LicenseDevice).filter(
        models.LicenseDevice.license_id == license.id,
        models.LicenseDevice.device_id == request.device_id
    ).first()

    if not existing_device:
        count = db.query(models.LicenseDevice).filter(models.LicenseDevice.license_id == license.id).count()
        allowed = license.license_type.allowed_devices
        if allowed is not None and count >= allowed:
            raise HTTPException(status_code=403, detail="Превышено число устройств")

        new_device = models.LicenseDevice(
            license_id=license.id,
            device_id=request.device_id,
            activated_at=datetime.now(timezone.utc)
        )
        db.add(new_device)
        db.commit()

    token_data = {
        "license_id": license.id,
        "device_id": request.device_id
    }
    access_token = create_access_token(token_data, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return LicenseActivateResponse(access_token=access_token)


@app.get("/verify")
def verify(credentials: HTTPAuthorizationCredentials = Security(security), db: Session = Depends(get_db)):
    payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
    license_id = payload.get("license_id")
    device_id = payload.get("device_id")
    license = db.query(License).filter(License.id == license_id).first()
    if not license:
        raise HTTPException(status_code=404, detail="Лицензия не найдена")
    if not license.is_active:
        raise HTTPException(status_code=403, detail="Лицензия не активна")

    # Проверка лимита устройств
    device_count = db.query(LicenseDevice).filter(LicenseDevice.license_id == license_id).count()
    allowed_devices = license.license_type.allowed_devices
    if device_count > allowed_devices:
        raise HTTPException(status_code=403, detail="Превышен лимит устройств")

    # Проверка устройства
    device = db.query(LicenseDevice).filter(
        LicenseDevice.license_id == license_id,
        LicenseDevice.device_id == device_id
    ).first()
    if not device:
        raise HTTPException(status_code=403, detail="Устройство не активировано")

    # Проверка срока действия
    if license.license_type.expires_days is not None:
        expiration_date = license.created_at + timedelta(days=license.license_type.expires_days)
        if expiration_date < datetime.now(timezone.utc):
            license.is_active = False
            db.commit()
            raise HTTPException(status_code=403, detail="Лицензия истекла")

    return {"status": "ok", "message": "Лицензия и устройство валидны"}


@app.post("/deactivate_device")
def deactivate_device(data: dict, db: Session = Depends(get_db)):
    user_id = data.get("user_id")  # Предполагается аутентификация
    device_id = data.get("device_id")
    license_id = data.get("license_id")

    # Проверяем, что устройство принадлежит пользователю
    license = db.query(License).filter(
        License.id == license_id,
        License.user_id == user_id
    ).first()
    if not license:
        raise HTTPException(status_code=404, detail="Лицензия не найдена или не принадлежит пользователю")

    device = db.query(LicenseDevice).filter(
        LicenseDevice.license_id == license_id,
        LicenseDevice.device_id == device_id
    ).first()
    if not device:
        raise HTTPException(status_code=404, detail="Устройство не найдено")

    db.delete(device)
    db.commit()
    return {"status": "ok", "message": "Устройство деактивировано"}