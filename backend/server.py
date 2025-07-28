import uuid

from fastapi import FastAPI, HTTPException, Depends, Security, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from backend.database import SessionLocal
from backend import models
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import jwt
import os
import logging
from dotenv import load_dotenv

from backend.models import LicenseDevice, LicenseType, License, User

app = FastAPI()
security = HTTPBearer()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

class LicenseChangeRequest(BaseModel):
    user_id: int
    new_license_key: str
    device_id: str

class LicenseCreate(BaseModel):
    user_id: int | None = None
    license_type_code: str
    license_key: str

class LicenseAssignRequest(BaseModel):
    user_id: int
    license_key: str

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
        expiration_date = license.created_at + timedelta(minutes=expires_days)
        if expiration_date < now:
            license.is_active = False
            db.commit()
            raise HTTPException(status_code=403, detail="Лицензия истекла")

# ------------------------ Эндпоинты ------------------------
@app.post("/activate_trial")
def activate_trial(device_id: str = Form(...), db: Session = Depends(get_db)):
    # Проверка, активирована ли пробная версия на этом устройстве
    existing_device = db.query(LicenseDevice).join(License).join(User).filter(
        LicenseDevice.device_id == device_id,
        License.license_type_code == "LICENSE-TRIAL"
    ).first()
    if existing_device:
        raise HTTPException(status_code=403, detail="Пробная версия уже была активирована на этом устройстве")

    # Создание нового пользователя, если его еще нет (автоинкрементный user_id)
    user = User()
    db.add(user)
    db.commit()  # Коммит для получения автоинкрементного id
    db.refresh(user)

    # Создание новой пробной лицензии с привязкой к user_id
    license = License(
        user_id=user.id,
        license_type_code="LICENSE-TRIAL",
        license_key=str(uuid.uuid4()),  # Генерация уникального ключа
        created_at=datetime.now(timezone.utc),
        is_active=True
    )
    db.add(license)
    db.commit()
    db.refresh(license)

    # Активация устройства
    license_device = LicenseDevice(license_id=license.id, device_id=device_id, activated_at=datetime.now(timezone.utc))
    db.add(license_device)
    db.commit()

    # Генерация токена
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"license_id": license.id, "device_id": device_id, "user_id": user.id},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

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

    license_type = db.query(models.LicenseType).filter(models.LicenseType.code == data.license_type_code).first()
    if not license_type:
        raise HTTPException(status_code=404, detail="Тип лицензии не найден")

    existing_license = db.query(models.License).filter(models.License.license_key == data.license_key).first()
    if existing_license:
        raise HTTPException(status_code=400, detail="Лицензия с таким ключом уже существует")

    license = models.License(
        user_id=None,
        license_type_code=data.license_type_code,
        license_key=data.license_key,
        created_at=datetime.now(timezone.utc),
        is_active=True
    )
    db.add(license)
    db.commit()
    db.refresh(license)
    return {"license_key": license.license_key, "user_id": None}
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
def change_license(data: LicenseChangeRequest, credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    logger.info(f"Смена лицензии: user_id={data.user_id}, new_license_key={data.new_license_key}, device_id={data.device_id}")

    # Декодирование токена для проверки user_id и device_id
    payload = verify_token(credentials.credentials)
    token_user_id = payload.get("user_id")
    token_device_id = payload.get("device_id")
    if not token_user_id or token_user_id != data.user_id:
        logger.error(f"Недействительный user_id: token_user_id={token_user_id}, data.user_id={data.user_id}")
        raise HTTPException(status_code=401, detail="Недействительный токен или user_id")
    if not token_device_id or token_device_id != data.device_id:
        logger.error(f"Недействительный device_id: token_device_id={token_device_id}, data.device_id={data.device_id}")
        raise HTTPException(status_code=401, detail="Недействительный токен или device_id")

    # Найти текущую активную лицензию
    old_license = db.query(models.License).filter(
        models.License.user_id == data.user_id,
        models.License.is_active == True
    ).first()

    # Найти новую лицензию
    new_license = db.query(models.License).filter(models.License.license_key == data.new_license_key).first()
    if not new_license:
        logger.error(f"Новая лицензия не найдена: license_key={data.new_license_key}")
        raise HTTPException(status_code=404, detail="Новая лицензия не найдена")

    # Проверяем лимит устройств для новой лицензии
    device_count = db.query(models.LicenseDevice).filter(models.LicenseDevice.license_id == new_license.id).count()
    old_devices = db.query(models.LicenseDevice).filter(models.LicenseDevice.license_id == old_license.id).all()
    allowed_devices = new_license.license_type.allowed_devices
    if allowed_devices is not None and device_count >= allowed_devices:
        logger.error(f"Превышен лимит устройств: device_count={device_count}, allowed_devices={allowed_devices}")
        raise HTTPException(status_code=403, detail="Превышен лимит устройств")

    if old_license.license_type_code == "LICENSE-TRIAL":
        old_license.is_active = False

    # Если старая лицензия платная, требуем AdminApp
    if old_license.license_type_code != "LICENSE-TRIAL":
        logger.error(f"Нельзя сменить платную лицензию через этот эндпоинт: license_id={old_license.id}, user_id={data.user_id}")
        raise HTTPException(status_code=403, detail="Смена платной лицензии возможна только через администратора")

    # Проверка и создание записи для устройства в новой лицензии
    existing = db.query(models.LicenseDevice).filter(
        models.LicenseDevice.license_id == new_license.id,
        models.LicenseDevice.device_id == data.device_id
    ).first()
    if not existing:
        new_device = models.LicenseDevice(
            license_id=new_license.id,
            device_id=data.device_id,
            activated_at=datetime.now(timezone.utc)
        )
        db.add(new_device)
        logger.info(f"Создано новое устройство для license_id={new_license.id}, device_id={data.device_id}")
    else:
        logger.info(f"Устройство уже существует в новой лицензии: device_id={data.device_id}, license_id={new_license.id}")

    if old_license.license_type_code == "LICENSE-TRIAL":
        new_license.user_id = data.user_id
        new_license.is_active = True
        new_license.created_at = datetime.now(timezone.utc)  # Сброс срока действия
        db.commit()

    # Генерация нового токена
    access_token = create_access_token(
        data={"license_id": new_license.id, "device_id": data.device_id, "user_id": data.user_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    logger.info(f"Лицензия изменена: user_id={data.user_id}, new_license_id={new_license.id}, device_id={data.device_id}")
    return {"message": "Лицензия изменена, устройство привязано", "access_token": access_token, "token_type": "bearer"}

@app.post("/activate", response_model=LicenseActivateResponse)
def activate_license(request: LicenseActivateRequest, db: Session = Depends(get_db)):
    # Найти новую лицензию по license_key
    license = db.query(models.License).filter(models.License.license_key == request.license_key).first()
    if not license:
        raise HTTPException(status_code=404, detail="Лицензия не найдена")

    if not license.is_active:
        raise HTTPException(status_code=403, detail="Лицензия не активна")

    old_license_device = db.query(models.LicenseDevice).join(models.License).filter(
        models.LicenseDevice.device_id == request.device_id,
        models.License.license_type_code == "LICENSE-TRIAL"
    ).first()

    user_id = None
    if old_license_device:
        old_license = old_license_device.license
        user_id = old_license.user_id

    existing_new_device = db.query(models.LicenseDevice).filter(
        models.LicenseDevice.license_id == license.id,
        models.LicenseDevice.device_id == request.device_id
    ).first()
    if existing_new_device:
        if license.user_id is None:
            raise HTTPException(status_code=400, detail="Лицензия не привязана к пользователю")
        token_data = {
            "license_id": license.id,
            "device_id": request.device_id,
            "user_id": license.user_id
        }
        access_token = create_access_token(token_data, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        return LicenseActivateResponse(access_token=access_token)

    device_count = db.query(models.LicenseDevice).filter(models.LicenseDevice.license_id == license.id).count()
    allowed_devices = license.license_type.allowed_devices
    if allowed_devices is not None and device_count >= allowed_devices:
        raise HTTPException(status_code=403, detail="Превышено число устройств")

    if license.user_id is None:
        if user_id is not None:
            license.user_id = user_id
        else:
            user = models.User()
            db.add(user)
            db.flush()
            license.user_id = user.id

    new_device = models.LicenseDevice(
        license_id=license.id,
        device_id=request.device_id,
        activated_at=datetime.now(timezone.utc)
    )
    db.add(new_device)
    db.commit()

    token_data = {
        "license_id": license.id,
        "device_id": request.device_id,
        "user_id": license.user_id
    }
    access_token = create_access_token(token_data, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return LicenseActivateResponse(access_token=access_token)

@app.get("/verify")
def verify(credentials: HTTPAuthorizationCredentials = Security(security), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
        license_id = payload.get("license_id")
        device_id = payload.get("device_id")
        print(f"[DEBUG] Verifying license_id={license_id}, device_id={device_id}")

        license = db.query(License).filter(License.id == license_id).first()
        if not license:
            print(f"[DEBUG] License not found for license_id={license_id}")
            raise HTTPException(status_code=404, detail="Лицензия не найдена")
        if not license.is_active:
            print(f"[DEBUG] License is not active: license_id={license_id}")
            raise HTTPException(status_code=403, detail="Лицензия не активна")

        # Проверка лимита устройств
        device_count = db.query(LicenseDevice).filter(LicenseDevice.license_id == license_id).count()
        allowed_devices = license.license_type.allowed_devices
        print(f"[DEBUG] Device count: {device_count}, Allowed devices: {allowed_devices}")
        if allowed_devices is not None and device_count > allowed_devices:
            print(f"[DEBUG] Device limit exceeded: {device_count} > {allowed_devices}")
            raise HTTPException(status_code=403, detail="Превышен лимит устройств")

        # Проверка устройства
        device = db.query(LicenseDevice).filter(
            LicenseDevice.license_id == license_id,
            LicenseDevice.device_id == device_id
        ).first()
        if not device:
            print(f"[DEBUG] Device not activated: device_id={device_id}")
            raise HTTPException(status_code=403, detail="Устройство не активировано")

        # Проверка срока действия
        if license.license_type.expires_days is not None:
            expiration_date = license.created_at + timedelta(minutes=license.license_type.expires_days)
            print(f"[DEBUG] Expiration check: expiration_date={expiration_date}, now={datetime.now(timezone.utc)}")
            if expiration_date < datetime.now(timezone.utc):
                license.is_active = False
                db.commit()
                print(f"[DEBUG] License expired: license_id={license_id}")
                raise HTTPException(status_code=403, detail="Лицензия истекла")

        print(f"[DEBUG] License verified successfully: license_id={license_id}")
        return {"status": "ok", "message": "Лицензия и устройство валидны"}
    except Exception as e:
        print(f"[DEBUG] Error in verify: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")


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