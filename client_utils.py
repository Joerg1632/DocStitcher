import sys

import jwt
from PyQt5.QtWidgets import QMessageBox
from datetime import datetime, timezone
from wmi import WMI
import multiprocessing as mp
import requests
from config import *
import pymupdf as fitz
from PIL import Image, ImageEnhance
import os
import tempfile
import random

def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath("")
    return os.path.join(base_path, relative_path)

def get_max_workers(page_count):
    cpu_count = mp.cpu_count()
    return cpu_count

def pt_to_px(pt, dpi):
    """Конвертирует пункты (pt) в пиксели (px) на основе DPI."""
    return int(pt * dpi / 72)

def get_device_id():
    """Получение уникального ID устройства с помощью machineid."""
    return WMI().Win32_ComputerSystemProduct()[0].UUID

def is_trial_valid(settings):
    license_token = settings.value("license_token")
    if not license_token:
        return False
    try:
        response = requests.get(f"{SERVER_URL}/verify", headers={"Authorization": f"Bearer {license_token}"})
        if response.status_code == 200:
            payload = jwt.decode(license_token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
            license_id = payload.get("license_id")
            license_response = requests.get(f"{SERVER_URL}/license/{license_id}", headers={"Authorization": f"Bearer {license_token}"})
            if license_response.status_code == 200:
                license_data = license_response.json()
                if license_data.get("license_type_code") == "LICENSE-TRIAL":
                    expires_days = license_data.get("expires_days", 2)
                    days_passed = (datetime.now(timezone.utc) - datetime.fromisoformat(
                        license_data.get("created_at"))).days
                    days_left = expires_days - days_passed
                    if days_left > 0:
                        QMessageBox.information(None, "Пробный период", f"Вы используете пробную версию.")
                        return True
                    else:
                        return False
                return False
            else:
                return False
        else:
            return False
    except (jwt.InvalidTokenError, requests.RequestException):
        return False

def verify_token(token, settings):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
        response = requests.get(f"{SERVER_URL}/verify", headers={"Authorization": f"Bearer {token}"})
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("status") == "updated":
                new_token = response_data.get("new_token")
                if new_token:
                    settings.setValue("license_token", new_token)
                    settings.sync()
                    print("[*] Токен обновлён в verify_token: устройство привязано к новой лицензии")
            return True
        elif response.status_code == 401 and response.json().get("detail") == "Токен истек":
            response = requests.post(
                f"{SERVER_URL}/refresh_token",
                json={"token": token},
                timeout=10
            )
            if response.status_code == 200:
                new_token = response.json().get("access_token")
                settings.setValue("license_token", new_token)
                settings.sync()
                return True
            else:
                return False
        return False
    except (jwt.InvalidTokenError, requests.RequestException) as e:
        return False

def activate_license(license_key, device_id):
    try:
        response = requests.post(f"{SERVER_URL}/activate", json={"license_key": license_key, "device_id": device_id})
        if response.status_code == 200:
            return response.json()["access_token"]
        else:
            error_detail = response.json().get("detail", "Ошибка активации")
            QMessageBox.critical(None, "Ошибка", f"Не удалось активировать лицензию: {error_detail}")
            return None
    except requests.RequestException as e:
        QMessageBox.critical(None, "Ошибка", f"Ошибка соединения с сервером: {str(e)}")
        return None

def deactivate_device(license_token, device_id):
    try:
        response = requests.post(
            f"{SERVER_URL}/deactivate_device",
            json={"device_id": device_id},
            headers={"Authorization": f"Bearer {license_token}"}
        )
        if response.status_code == 200:
            return True
        else:
            error_detail = response.json().get("detail", "Ошибка деактивации")
            QMessageBox.critical(None, "Ошибка", f"Не удалось деактивировать устройство: {error_detail}")
            return False
    except requests.RequestException as e:
        QMessageBox.critical(None, "Ошибка", f"Ошибка соединения с сервером: {str(e)}")
        return False

def change_license(license_token, data):
    try:
        headers = {"Authorization": f"Bearer {license_token}"}
        response = requests.post(f"{SERVER_URL}/change_license", json=data, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()["access_token"]
        else:
            error_detail = response.json().get("detail", "Ошибка смены лицензии")
            QMessageBox.critical(None, "Ошибка", f"Не удалось сменить лицензию: {error_detail}")
            return None
    except requests.RequestException as e:
        QMessageBox.critical(None, "Ошибка", f"Ошибка соединения с сервером: {str(e)}")
        return None

def process_page(page_num, doc_path, a4_width_px, a4_height_px, dpi, ribbon_position, first_page_count,
                 checkbox_bw, ribbon_path, ribbon_left_path, ribbon_middle_path, dot1_path, dot2_path,
                 dot_mid_path):
    """Обрабатывает одну страницу в отдельном процессе."""
    try:

        doc = fitz.open(doc_path)
        page = doc.load_page(page_num)
        pix = page.get_pixmap(alpha=False, dpi=dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()

        if page_num < first_page_count and checkbox_bw:
            img = img.convert("L")

        margin_px = pt_to_px(5, dpi)
        max_width = a4_width_px - 2 * margin_px
        max_height = a4_height_px - 2 * margin_px
        scale = min(max_width / img.width, max_height / img.height)
        new_width = int(img.width * scale)
        new_height = int(img.height * scale)
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        enhancer = ImageEnhance.Sharpness(img_resized)
        img_resized = enhancer.enhance(1.3)

        new_img = Image.new("RGB", (a4_width_px, a4_height_px), (255, 255, 255))
        x_offset = (a4_width_px - new_width) // 2
        y_offset = (a4_height_px - new_height) // 2
        new_img.paste(img_resized, (x_offset, y_offset))

        if page_num == 0:
            ribbon_scale = 0.6
            if ribbon_position == "Слева" and os.path.exists(ribbon_left_path):
                ribbon = Image.open(ribbon_left_path).convert("RGBA")
                ribbon_width = int(ribbon.width * ribbon_scale)
                ribbon_height = int(ribbon.height * ribbon_scale)
                ribbon_resized = ribbon.resize((ribbon_width, ribbon_height), Image.Resampling.LANCZOS)
                ribbon_x = x_offset - pt_to_px(3.09, dpi)
                ribbon_y = y_offset + pt_to_px(40, dpi)
                new_img.paste(ribbon_resized, (ribbon_x, ribbon_y), ribbon_resized)
            elif ribbon_position == "По середине" and os.path.exists(ribbon_middle_path):
                ribbon_scale = 0.7
                ribbon = Image.open(ribbon_middle_path).convert("RGBA")
                ribbon_width = int(ribbon.width * ribbon_scale)
                ribbon_height = int(ribbon.height * ribbon_scale)
                ribbon_resized = ribbon.resize((ribbon_width, ribbon_height), Image.Resampling.LANCZOS)
                ribbon_x = x_offset
                ribbon_y = y_offset + (new_height // 2) - ribbon_height // 2
                new_img.paste(ribbon_resized, (ribbon_x, ribbon_y), ribbon_resized)
            else:
                ribbon = Image.open(ribbon_path).convert("RGBA")
                ribbon_width = int(ribbon.width * ribbon_scale)
                ribbon_height = int(ribbon.height * ribbon_scale)
                ribbon_resized = ribbon.resize((ribbon_width, ribbon_height), Image.Resampling.LANCZOS)
                ribbon_x = x_offset + pt_to_px(51, dpi)
                ribbon_y = y_offset - pt_to_px(2.74, dpi)
                new_img.paste(ribbon_resized, (ribbon_x, ribbon_y), ribbon_resized)
        elif os.path.exists(dot1_path) and os.path.exists(dot2_path):
            if ribbon_position == "Слева" or ribbon_position == "Сверху":
                dot_file = random.choice([dot1_path, dot2_path])
                dot = Image.open(dot_file).convert("RGBA")
                dot_width = pt_to_px(16, dpi)
                dot_height = pt_to_px(16, dpi)
                dot = dot.resize((dot_width, dot_height), Image.Resampling.LANCZOS)
                if ribbon_position == "Слева":
                    dot_x = x_offset + pt_to_px(17, dpi)
                    dot_y = y_offset + pt_to_px(40, dpi)
                else:
                    dot_x = x_offset + pt_to_px(59, dpi)
                    dot_y = y_offset + pt_to_px(30, dpi)
                new_img.paste(dot, (dot_x, dot_y), dot)
            elif ribbon_position == "По середине" and os.path.exists(dot_mid_path):
                dot = Image.open(dot_mid_path).convert("RGBA")
                original_width, original_height = dot.size
                scale_height = new_height / original_height
                new_dot_height = new_height
                new_dot_width = int(original_width * scale_height)
                dot_resized = dot.resize((new_dot_width, new_dot_height), Image.Resampling.LANCZOS)
                dot_x = x_offset
                dot_y = y_offset
                new_img.paste(dot_resized, (dot_x, dot_y), dot_resized)

        temp_img_path = os.path.join(tempfile.gettempdir(), next(tempfile._get_candidate_names()) + ".jpg")
        new_img.save(temp_img_path, "JPEG", dpi=(dpi, dpi), quality=100, subsampling=0, optimize=True)
        return page_num, temp_img_path
    except Exception as e:
        print(f"[!] Ошибка при обработке страницы {page_num}: {e}")
        return page_num, None

