from fastapi import FastAPI, HTTPException, Depends
from fastapi.params import Security
from pydantic import BaseModel
from database import SessionLocal
import models
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import jwt
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
import os

app = FastAPI()
security = HTTPBearer()

SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 дней

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# ------------------------ Pydantic модели ------------------------

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class LicenseCreate(BaseModel):
    license_key: str
    allowed_devices: int | None = None
    expires_days: int | None = None  # None — бессрочная лицензия

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
    now = datetime.now(timezone.utc)  # timezone-aware текущее UTC время

    expires_days = license.license_type.expires_days
    if expires_days is not None:
        expiration_date = license.created_at.replace(tzinfo=timezone.utc) + timedelta(days=expires_days)
        if expiration_date < now:
            # Деактивируем лицензию, если она просрочена
            license.is_active = False
            db.commit()
            raise HTTPException(status_code=403, detail="Лицензия истекла")
# ------------------------ Эндпоинты ------------------------

@app.post("/create_user")
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")
    user = models.User(
        username=data.username,
        email=data.email,
        password_hash=data.password  # TODO: Хешировать пароль!
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user_id": user.id, "message": "User created successfully"}


@app.post("/create_license")
def create_license(data: LicenseCreate, db: Session = Depends(get_db)):
    existing = db.query(models.License).filter(models.License.license_key == data.license_key).first()
    if existing:
        raise HTTPException(status_code=400, detail="License key already exists")

    license = models.License(
        license_key=data.license_key,
        # allowed_devices больше не в License, а в LicenseType —
        # тут можно игнорировать или брать из LicenseType, если создаёшь и тип лицензии тоже
        created_at=datetime.now(timezone.utc),
        user_id=None,  # Пока не назначено
        is_active=True
    )
    # Здесь стоит связать license с license_type, например через license_type_code
    # Чтобы allowed_devices и expires_days были корректными — это должно быть в LicenseType

    db.add(license)
    db.commit()
    return {"message": "License created successfully"}


@app.post("/assign_license")
def assign_license(data: LicenseAssignRequest, db: Session = Depends(get_db)):
    license = db.query(models.License).filter(models.License.license_key == data.license_key).first()
    if not license:
        raise HTTPException(status_code=404, detail="Лицензия не найдена")
    if license.user_id is not None:
        raise HTTPException(status_code=400, detail="Лицензия уже назначена другому пользователю")

    license.user_id = data.user_id
    db.commit()
    return {"message": f"Лицензия назначена пользователю {data.user_id}"}


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

    # Проверяем просрочку старой лицензии
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

    return {"message": "Лицензия успешно изменена, устройства перенесены"}

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

    if not license.is_active:
        raise HTTPException(status_code=403, detail="Лицензия не активна")

    check_license_expiration(license, db)

    device = db.query(models.LicenseDevice).filter(
        models.LicenseDevice.license_id == license.id,
        models.LicenseDevice.device_id == device_id
    ).first()

    if not device:
        raise HTTPException(status_code=403, detail="Устройство не активировано")

    return {"status": "ok", "message": "Лицензия и устройство валидны"}