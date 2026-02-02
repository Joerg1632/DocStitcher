import uuid

from fastapi import FastAPI, HTTPException, Depends, Security, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from backend.dbase import SessionLocal
from backend import models
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timedelta, timezone
import jwt
import os
import logging
from dotenv import load_dotenv

from backend.models import LicenseDevice, LicenseType, License

app = FastAPI()
security = HTTPBearer()

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s %(name)s: %(message)s',
)

logger = logging.getLogger(__name__)

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY не установлен в переменных окружения")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

class TokenRefreshRequest(BaseModel):
    token: str

class LicenseChangeRequest(BaseModel):
    new_license_key: str
    device_id: str

class LicenseCreate(BaseModel):
    license_type_code: str
    license_key: str

class LicenseAssignRequest(BaseModel):
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

def create_access_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def check_license_expiration(license, db: Session):
    now = datetime.now(timezone.utc)
    expires_days = license.license_type.expires_days
    if expires_days is not None:
        expiration_date = license.created_at + timedelta(days=expires_days)
        if expiration_date < now:
            license.is_active = False
            db.commit()
            raise HTTPException(status_code=403, detail="Лицензия истекла")

@app.post("/activate_trial")
def activate_trial(device_id: str = Form(...), db: Session = Depends(get_db)):
    # Проверка, активирована ли пробная версия на этом устройстве
    existing_device = db.query(LicenseDevice).join(License).filter(
        LicenseDevice.device_id == device_id,
        License.license_type_code == "LICENSE-TRIAL"
    ).first()
    if existing_device:
        raise HTTPException(status_code=403, detail="Пробная версия уже была активирована на этом устройстве")

    license = License(
        license_type_code="LICENSE-TRIAL",
        license_key=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        is_active=True
    )
    db.add(license)
    db.commit()
    db.refresh(license)

    current_license_device = db.query(LicenseDevice).filter(
        LicenseDevice.device_id == device_id
    ).first()

    if current_license_device:
        old_license_id = current_license_device.license_id
        current_license_device.license_id = license.id
        current_license_device.activated_at = datetime.now(timezone.utc)
        db.commit()

        remaining_devices = db.query(LicenseDevice).filter(
            LicenseDevice.license_id == old_license_id
        ).count()
        old_license = db.query(License).filter(License.id == old_license_id).first()

        if remaining_devices == 0 and old_license and not old_license.is_active:
            db.delete(old_license)
            db.commit()
    else:
        license_device = LicenseDevice(
            license_id=license.id,
            device_id=device_id,
            activated_at=datetime.now(timezone.utc)
        )
        db.add(license_device)
        db.commit()

    access_token_expires = timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    access_token = create_access_token(
        data={"license_id": license.id, "device_id": device_id},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/license/{license_id}")
async def get_license(license_id: int, credentials: HTTPAuthorizationCredentials = Security(security),
                      db: Session = Depends(get_db)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})  # Игнорируем exp
        if payload.get("license_id") != license_id:
            raise HTTPException(status_code=401, detail="Токен не соответствует лицензии")

        license = db.query(models.License).options(joinedload(models.License.license_type)).filter(
            models.License.id == license_id).first()
        if not license or not license.is_active:
            raise HTTPException(status_code=404, detail="Лицензия не найдена или неактивна")

        check_license_expiration(license, db)

        return {
            "license_id": license.id,
            "license_type_code": license.license_type_code,
            "created_at": license.created_at.isoformat(),
            "expires_days": license.license_type.expires_days,
            "is_active": license.is_active
        }
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Невалидный токен")

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
        license_type_code=data.license_type_code,
        license_key=data.license_key,
        created_at=datetime.now(timezone.utc),
        is_active=True
    )
    db.add(license)
    db.commit()
    db.refresh(license)
    return {"license_key": license.license_key}

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
    logger.error(f"Смена лицензии: new_license_key={data.new_license_key}, device_id={data.device_id}")

    # Проверка токена
    payload = verify_token(credentials.credentials)
    if payload.get("device_id") != data.device_id:
        raise HTTPException(status_code=401, detail="Недействительный токен или device_id")

    # Находим старую лицензию, которая по любому активна
    old_license_id = payload.get("license_id")
    old_license = db.query(models.License).filter(
        models.License.id == old_license_id,
        models.License.is_active == True
    ).first()
    if not old_license:
        raise HTTPException(status_code=404, detail="Старая лицензия не найдена или не активна")

    # Находим новую лицензию
    new_license = db.query(models.License).filter(
        models.License.license_key == data.new_license_key
    ).first()
    if not new_license:
        raise HTTPException(status_code=404, detail="Новая лицензия не найдена")
    if old_license.id == new_license.id:
        raise HTTPException(status_code=400, detail="Нельзя сменить на ту же лицензию")
    if not new_license.is_active:
        raise HTTPException(status_code=403, detail="Новая лицензия не активна")

    check_license_expiration(new_license, db)

    # Получаем доступное число устройств на новой лицензии и общее число устройств, привязанное к старой
    allowed_devices = new_license.license_type.allowed_devices
    current_device_count = db.query(models.LicenseDevice).filter(
        models.LicenseDevice.license_id == new_license.id
    ).count()

    # Получить все устройства старой лицензии
    old_devices = db.query(models.LicenseDevice).filter(
        models.LicenseDevice.license_id == old_license.id
    ).all()

    logger.info(f"Devices count to transfer: {len(old_devices)}")

    if allowed_devices is not None and (current_device_count + len(old_devices)) > allowed_devices:
        raise HTTPException(status_code=403,
                            detail="Недостаточно слотов в новой лицензии для переноса устройств, деактивируйте лицензию на лишних устройствах вручную")

    if old_license.license_type.code == "LICENSE-TRIAL":
        new_device = models.LicenseDevice(
            license_id=new_license.id,
            device_id=data.device_id,
            activated_at=datetime.now(timezone.utc)
        )
        db.add(new_device)
        old_license.is_active = False
        logger.info("Пробная лицензия деактивирована")

    else:
        for dev in old_devices:
            logger.info(f"Before change: device id={dev.id}, license_id={dev.license_id}")
            dev.license_id = new_license.id
            logger.info(f"After change: device id={dev.id}, license_id={dev.license_id}")
        logger.info("Старая лицензия удалена")
        db.flush()

        db.delete(old_license)

    db.commit()

    return {
        "message": "Лицензия успешно сменена",
        "access_token": create_access_token(
            data={"license_id": new_license.id, "device_id": data.device_id},
            expires_delta=timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
        ),
        "token_type": "bearer"
    }

@app.post("/activate", response_model=LicenseActivateResponse)
def activate_license(request: LicenseActivateRequest, db: Session = Depends(get_db)):
    # Найти новую лицензию по license_key
    license = db.query(models.License).filter(models.License.license_key == request.license_key).first()
    if not license:
        raise HTTPException(status_code=404, detail="Лицензия не найдена")
    if not license.is_active:
        raise HTTPException(status_code=403, detail="Лицензия не активна")

    check_license_expiration(license, db)

    existing_new_device = db.query(models.LicenseDevice).filter(
        models.LicenseDevice.license_id == license.id,
        models.LicenseDevice.device_id == request.device_id
    ).first()
    if existing_new_device:
        token_data = {
            "license_id": license.id,
            "device_id": request.device_id
        }
        access_token = create_access_token(token_data, timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
        return LicenseActivateResponse(access_token=access_token)

    device_count = db.query(models.LicenseDevice).filter(models.LicenseDevice.license_id == license.id).count()
    allowed_devices = license.license_type.allowed_devices
    if allowed_devices is not None and device_count >= allowed_devices:
        raise HTTPException(status_code=403, detail="Превышено число устройств")

    old_device_entry = db.query(models.LicenseDevice).join(models.License).filter(
        models.LicenseDevice.device_id == request.device_id,
        models.License.license_type_code != "LICENSE-TRIAL",
        models.License.id != license.id
    ).first()

    if old_device_entry:
        old_license = old_device_entry.license
        old_device_entry.license_id = license.id
        old_device_entry.activated_at = datetime.now(timezone.utc)
        db.commit()

        remaining_devices = db.query(models.LicenseDevice).filter(
            models.LicenseDevice.license_id == old_license.id
        ).count()

        if remaining_devices == 0:
            db.delete(old_license)
            logger.info("Старая лицензия удалена (пуста)")
    else:
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
    }
    access_token = create_access_token(token_data, timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    return LicenseActivateResponse(access_token=access_token)

@app.get("/verify")
def verify(credentials: HTTPAuthorizationCredentials = Security(security), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        license_id = payload.get("license_id")
        device_id = payload.get("device_id")
        if not license_id or not device_id:
            print(f"[DEBUG] Invalid token: missing license_id or device_id")
            raise HTTPException(status_code=401, detail="Недействительный токен: отсутствует license_id или device_id")

        # Проверяем, привязано ли устройство к активной лицензии
        license_device = db.query(LicenseDevice).join(License).filter(
            LicenseDevice.device_id == device_id,
            License.is_active == True
        ).first()

        if not license_device:
            print(f"[DEBUG] Device not activated: device_id={device_id}")
            raise HTTPException(status_code=401, detail="Устройство не привязано к активной лицензии")

        current_license_id = license_device.license_id
        license = db.query(License).filter(License.id == current_license_id).first()
            # Проверяем срок действия лицензии
        check_license_expiration(license, db)

        # Проверяем, совпадает ли license_id из токена с текущей лицензией
        if current_license_id == license_id:
            # Токен актуален
            print(f"[DEBUG] License verified successfully: license_id={license_id}")
            return {"status": "valid", "license_id": license_id, "device_id": device_id}
        else:
            # Устройство привязано к другой лицензии, генерируем новый токен
            print(f"[DEBUG] Token outdated: generating new token for license_id={current_license_id}")
            access_token_expires = timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
            new_token = create_access_token(
                data={"license_id": current_license_id, "device_id": device_id},
                expires_delta=access_token_expires
            )
            return {
                "status": "updated",
                "license_id": current_license_id,
                "device_id": device_id,
                "new_token": new_token
            }

    except jwt.ExpiredSignatureError:
        print(f"[DEBUG] Token expired")
        raise HTTPException(status_code=401, detail="Токен истек")
    except jwt.InvalidSignatureError:
        print(f"[DEBUG] Invalid token: invalid signature")
        raise HTTPException(status_code=401, detail="Недействительный токен: неверная подпись")
    except jwt.InvalidTokenError as e:
        print(f"[DEBUG] Invalid token: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Недействительный токен: {str(e)}")
    except Exception as e:
        print(f"[DEBUG] Error in verify: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")

@app.post("/deactivate_device")
async def deactivate_device(data: dict, credentials: HTTPAuthorizationCredentials = Security(security), db: Session = Depends(get_db)):
    try:
        token = credentials.credentials
        payload = verify_token(token)
        license_id = payload.get("license_id")
        device_id = data.get("device_id")
        logger.info(f"[DEBUG] Deactivating device: license_id={license_id}, device_id={device_id}")

        if not device_id:
            raise HTTPException(status_code=400, detail="device_id обязателен")

        # Ищем устройство для данной лицензии
        license_devices = db.query(models.LicenseDevice).filter(
            models.LicenseDevice.license_id == license_id,
            models.LicenseDevice.device_id == device_id
        ).all()

        if not license_devices:
            logger.info(f"[DEBUG] Device not found for license_id={license_id}, device_id={device_id}")
            raise HTTPException(status_code=404, detail="Устройство не найдено для данной лицензии")

        deleted_count = 0
        for device in license_devices:
            license = db.query(models.License).filter(models.License.id == device.license_id).first()
            if license and license.license_type_code == "LICENSE-TRIAL":
                logger.info(f"[DEBUG] Skipping trial license device: license_id={license.id}")
                continue  # Не удаляем устройства для пробных лицензий
            db.delete(device)
            deleted_count += 1

        db.commit()
        logger.info(f"[DEBUG] Device deactivated: deleted_count={deleted_count}")
        return {
            "status": "ok",
            "message": f"Устройство деактивировано. Удалено записей: {deleted_count}, пробные лицензии сохранены (если были)"
        }
    except jwt.PyJWTError as e:
        logger.error(f"[ERROR] JWT error in deactivate_device: {str(e)}")
        raise HTTPException(status_code=401, detail="Ошибка сервера, попробуйте позже")
    except Exception as e:
        logger.error(f"[ERROR] Unexpected error in deactivate_device: {str(e)}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера, попробуйте позже")

@app.post("/refresh_token")
async def refresh_token(token_data: dict, db: Session = Depends(get_db)):
    try:
        token = token_data.get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Токен не предоставлен")

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        device_id = payload.get("device_id")
        if not device_id:
            raise HTTPException(status_code=401, detail="Невалидный токен")

        logger.info(f"[DEBUG] Refreshing token for device_id={device_id}")
        # Проверяем текущую привязку устройства
        license_device = db.query(models.LicenseDevice).join(models.License).filter(
            models.LicenseDevice.device_id == device_id,
            models.License.is_active == True
        ).first()
        if not license_device:
            logger.info(f"[DEBUG] Device not associated with any active license: device_id={device_id}")
            raise HTTPException(status_code=401, detail="Устройство не связано с активной лицензией")

        license = db.query(models.License).filter(models.License.id == license_device.license_id).first()
        check_license_expiration(license, db)

        new_token_data = {"license_id": license_device.license_id, "device_id": device_id}
        new_token = create_access_token(new_token_data, expires_delta=timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
        logger.info(f"[DEBUG] New token created for license_id={license_device.license_id}")
        return {"access_token": new_token}
    except jwt.PyJWTError as e:
        logger.error(f"[ERROR] JWT error in refresh_token: {str(e)}")
        raise HTTPException(status_code=401, detail="Невалидный токен")
    except Exception as e:
        logger.error(f"[ERROR] Unexpected error in refresh_token: {str(e)}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")