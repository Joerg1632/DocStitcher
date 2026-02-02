import requests
import jwt
from PyQt5.QtWidgets import QMessageBox, QInputDialog, QDialog, QLineEdit, QDialogButtonBox, QSpacerItem, QSizePolicy, \
    QWidget
from PyQt5.QtCore import QSettings, Qt
from datetime import datetime, timezone, timedelta
from client.client_utils import get_device_id, deactivate_device, change_license
from config import *

def update_license_status(window):
    settings = QSettings("YourCompany", "DocStitcher")
    license_token = settings.value("license_token")
    if license_token:
        try:
            response = requests.get(f"{SERVER_URL}/verify", headers={"Authorization": f"Bearer {license_token}"})
            if response.status_code == 200:
                payload = jwt.decode(license_token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
                license_id = payload.get("license_id")
                license_response = requests.get(f"{SERVER_URL}/license/{license_id}",
                                               headers={"Authorization": f"Bearer {license_token}"})
                if license_response.status_code == 200:
                    license_data = license_response.json()
                    expires_days = license_data.get("expires_days")
                    created_at = datetime.fromisoformat(license_data.get("created_at"))
                    now = datetime.now(timezone.utc)
                    time_passed = now - created_at
                    days_left = expires_days - time_passed.days if expires_days is not None else None
                    time_left = timedelta(days=expires_days) - time_passed if expires_days is not None else None

                    if license_data.get("license_type_code") == "LICENSE-UNLIMITED":
                        window.license_status = "Лицензировано"
                        window.setWindowTitle("DocStitcher (Лицензировано)")
                    elif days_left is not None:
                        if time_left.total_seconds() < 24 * 3600:  # Less than 24 hours
                            window.license_status = "Лицензия истекает сегодня"
                            window.setWindowTitle("DocStitcher (Лицензия истекает сегодня)")
                        elif days_left > 7:
                            window.license_status = "Лицензировано"
                            window.setWindowTitle("DocStitcher (Лицензировано)")
                        elif days_left == 1:
                            window.license_status = "До конца лицензии 1 день"
                            window.setWindowTitle("DocStitcher (До конца лицензии 1 день)")
                        else:
                            window.license_status = f"До конца лицензии {days_left} дн."
                            window.setWindowTitle(f"DocStitcher (До конца лицензии {days_left} дн.)")
                    else:
                        window.license_status = "Лицензировано"
                        window.setWindowTitle("DocStitcher (Лицензировано)")
                else:
                    window.license_status = "Лицензия недействительна"
                    window.setWindowTitle("DocStitcher (Лицензия недействительна)")
            else:
                window.license_status = "Лицензия недействительна"
                window.setWindowTitle("DocStitcher (Лицензия недействительна)")
        except (jwt.InvalidTokenError, requests.RequestException) as e:
            window.license_status = "Лицензия недействительна"
            window.setWindowTitle("DocStitcher (Лицензия недействительна)")
            print(f"[!] Ошибка проверки лицензии: {e}")
    else:
        window.license_status = "Не активировано"
        window.setWindowTitle("DocStitcher (Не активировано)")
    window.update_action_states()

def check_license_periodically(window):
    from run import WelcomeDialog
    settings = QSettings("YourCompany", "DocStitcher")
    device_id = get_device_id()
    license_token = settings.value("license_token")

    if not license_token:
        window.license_status = "Не активировано"
        window.setWindowTitle("DocStitcher (Не активировано)")
        window.hide()
        welcome_dialog = WelcomeDialog(settings, device_id)
        if welcome_dialog.exec_() == QDialog.Accepted:
            update_license_status(window)
            window.show()
        else:
            window.close()
        return

    try:
        payload = jwt.decode(license_token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
        exp_timestamp = payload.get("exp")
        if exp_timestamp:
            exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            print(exp_datetime, now)
            if (exp_datetime - now).days < 1:
                response = requests.post(
                    f"{SERVER_URL}/refresh_token",
                    json={"token": license_token},
                    timeout=10
                )
                if response.status_code == 200:
                    new_token = response.json().get("access_token")
                    settings.setValue("license_token", new_token)
                    license_token = new_token
                    print("[*] Токен успешно обновлён")
                else:
                    print(f"[!] Ошибка при обновлении токена: {response.status_code}")
                    window.license_status = "Лицензия недействительна"
                    window.setWindowTitle("DocStitcher (Лицензия недействительна)")
                    window.hide()
                    welcome_dialog = WelcomeDialog(settings, device_id)
                    if welcome_dialog.exec_() == QDialog.Accepted:
                        update_license_status(window)
                        window.show()
                    else:
                        window.close()
                    return

        response = requests.get(f"{SERVER_URL}/verify", headers={"Authorization": f"Bearer {license_token}"})
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("status") == "updated":
                # Сервер вернул новый токен, так как устройство привязано к другой лицензии
                new_token = response_data.get("new_token")
                if new_token:
                    settings.setValue("license_token", new_token)
                    license_token = new_token
                    print("[*] Токен обновлён: устройство привязано к новой лицензии")

            payload = jwt.decode(license_token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
            license_id = payload.get("license_id")
            license_response = requests.get(
                f"{SERVER_URL}/license/{license_id}",
                headers={"Authorization": f"Bearer {license_token}"}
            )
            if license_response.status_code == 200:
                license_data = license_response.json()
                expires_days = license_data.get("expires_days")
                created_at = datetime.fromisoformat(license_data.get("created_at"))
                now = datetime.now(timezone.utc)
                time_passed = now - created_at
                days_left = expires_days - time_passed.days if expires_days is not None else None
                time_left = timedelta(days=expires_days) - time_passed if expires_days is not None else None

                if time_left is not None and time_left.total_seconds() <= 0:
                    window.license_status = "Лицензия истекает сегодня"
                    window.setWindowTitle("DocStitcher (Лицензия истекает сегодня)")
                    QMessageBox.critical(window, "Лицензия истекла",
                                         "Ваша лицензия истекла. Пожалуйста, активируйте новую лицензию.")
                    window.hide()
                    welcome_dialog = WelcomeDialog(settings, device_id)
                    if welcome_dialog.exec_() == QDialog.Accepted:
                        update_license_status(window)
                        window.show()
                    else:
                        window.close()
                else:
                    if days_left is None or days_left > 7:
                        window.license_status = "Лицензировано"
                        window.setWindowTitle("DocStitcher (Лицензировано)")
                    elif time_left.total_seconds() < 24 * 3600:
                        window.license_status = "Лицензия истекает сегодня"
                        window.setWindowTitle("DocStitcher (Лицензия истекает сегодня)")
                    elif days_left == 1:
                        window.license_status = "До конца лицензии 1 день"
                        window.setWindowTitle("DocStitcher (До конца лицензии 1 день)")
                    else:
                        window.license_status = f"До конца лицензии {days_left} дн."
                        window.setWindowTitle(f"DocStitcher (До конца лицензии {days_left} дн.)")
            else:
                window.license_status = "Лицензия недействительна"
                window.setWindowTitle("DocStitcher (Лицензия недействительна)")
                window.hide()
                welcome_dialog = WelcomeDialog(settings, device_id)
                if welcome_dialog.exec_() == QDialog.Accepted:
                    update_license_status(window)
                    window.show()
                else:
                    window.close()
        else:
            window.license_status = "Лицензия недействительна"
            window.setWindowTitle("DocStitcher (Лицензия недействительна)")
            window.hide()
            welcome_dialog = WelcomeDialog(settings, device_id)
            if welcome_dialog.exec_() == QDialog.Accepted:
                update_license_status(window)
                window.show()
            else:
                window.close()
    except (jwt.InvalidTokenError, requests.RequestException) as e:
        print(f"[!] Ошибка проверки лицензии: {e}")
        window.license_status = "Лицензия недействительна"
        window.setWindowTitle("DocStitcher (Лицензия недействительна)")
        window.hide()
        welcome_dialog = WelcomeDialog(settings, device_id)
        if welcome_dialog.exec_() == QDialog.Accepted:
            update_license_status(window)
            window.show()
        else:
            window.close()

def deactivate_device_action(window):
    settings = QSettings("YourCompany", "DocStitcher")
    license_token = settings.value("license_token")
    device_id = get_device_id()

    msg = QMessageBox(window)
    msg.setWindowTitle("Подтверждение деактивации")
    msg.setText("Вы хотите деактивировать лицензию на этом устройстве?")

    yes_button = msg.addButton("Да", QMessageBox.AcceptRole)
    no_button = msg.addButton("Отменить", QMessageBox.RejectRole)

    label = msg.findChild(QWidget, "qt_msgbox_label")
    if label:
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)

    button_box = msg.findChild(QWidget, "qt_msgbox_buttonbox")
    if button_box:
        layout = button_box.layout()
        layout.removeWidget(yes_button)
        layout.removeWidget(no_button)

        layout.addWidget(yes_button)
        spacer = QSpacerItem(200, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addItem(spacer)
        layout.addWidget(no_button)

    msg.resize(150, msg.sizeHint().height())

    msg.exec_()

    if msg.clickedButton() == yes_button:
        if deactivate_device(license_token, device_id):
            settings.remove("license_token")
            QMessageBox.information(window, "Успех", "Устройство успешно деактивировано.")
            update_license_status(window)
    window.update_action_states()

def on_change_license_clicked(window):
    settings = QSettings("YourCompany", "DocStitcher")
    license_token = settings.value("license_token")
    if not license_token:
        QMessageBox.warning(window, "Ошибка", "Токен лицензии не найден. Сначала активируйте лицензию.")
        return

    dialog = QInputDialog(window)
    dialog.setWindowTitle("Смена лицензии")
    dialog.setLabelText(
        "<b>Введите ключ</b><br><br>"
        "<span style='font-size: 11px; color: gray;'>"
        "Если к текущей лицензии привязаны другие устройства, "
        "они также перейдут на новую лицензию при наличии свободных мест."
        "</span>"
    )
    dialog.setInputMode(QInputDialog.TextInput)
    dialog.setTextEchoMode(QLineEdit.Normal)
    dialog.resize(290, 100)
    dialog.setStyleSheet("QLabel { qproperty-wordWrap: true; }")


    dialog.setOkButtonText("Ок")
    dialog.setCancelButtonText("Отменить")

    button_box = dialog.findChild(QDialogButtonBox)
    if button_box:
        layout = button_box.layout()
        ok_button = button_box.button(QDialogButtonBox.Ok)
        cancel_button = button_box.button(QDialogButtonBox.Cancel)
        layout.removeWidget(ok_button)
        layout.removeWidget(cancel_button)

        layout.addWidget(ok_button)
        spacer = QSpacerItem(200, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addItem(spacer)
        layout.addWidget(cancel_button)

    if not dialog.exec_():
        return

    new_license_key = dialog.textValue().strip()
    if not new_license_key:
        QMessageBox.warning(window, "Ошибка", "Не введён новый ключ лицензии.")
        return

    try:
        payload = jwt.decode(license_token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
        device_id = payload.get("device_id")
        if device_id is None:
            QMessageBox.warning(window, "Ошибка", "Невозможно извлечь device_id из токена. Проверьте токен.")
            return

        data = {
            "new_license_key": new_license_key,
            "device_id": device_id
        }
        new_token = change_license(license_token, data)
        if new_token:
            settings.setValue("license_token", new_token)
            update_license_status(window)
            QMessageBox.information(window, "Успех", "Лицензия успешно обновлена.")
    except jwt.InvalidTokenError:
        QMessageBox.warning(window, "Ошибка", "Недействительный токен лицензии.")
    except Exception as e:
        QMessageBox.warning(window, "Ошибка", f"Произошла неизвестная ошибка: {str(e)}")

    window.update_action_states()

def show_license_info(window):
    settings = QSettings("YourCompany", "DocStitcher")
    license_token = settings.value("license_token")
    device_id = get_device_id()
    if license_token:
        try:
            response = requests.get(f"{SERVER_URL}/verify", headers={"Authorization": f"Bearer {license_token}"})
            if response.status_code == 200:
                payload = jwt.decode(license_token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
                license_id = payload.get("license_id")
                license_response = requests.get(f"{SERVER_URL}/license/{license_id}",
                                               headers={"Authorization": f"Bearer {license_token}"})
                if license_response.status_code == 200:
                    license_data = license_response.json()
                    license_type_code = license_data.get("license_type_code")
                    code_to_name = {
                        "LICENSE-UNLIMITED": "Безлимитная лицензия",
                        "LICENSE-TRIAL": "Пробная версия 1 устройство (2 дня)",
                        "LICENSE-1-MONTH": "Лицензия на 1 устройство (1 месяц)",
                        "LICENSE-5-MONTH": "Лицензия на 5 устройств (1 месяц)",
                        "LICENSE-15-MONTH": "Лицензия на 15 устройств (1 месяц)",
                        "LICENSE-1-YEAR": "Лицензия на 1 устройство (1 год)",
                        "LICENSE-5-YEAR": "Лицензия на 5 устройств (1 год)",
                        "LICENSE-15-YEAR": "Лицензия на 15 устройств (1 год)"
                    }
                    license_name = code_to_name.get(license_type_code, "Неизвестный тип лицензии")
                    QMessageBox.information(
                        window,
                        "Информация о лицензии",
                        f"Тип лицензии: {license_name}\nID устройства: {device_id}"
                    )
                else:
                    QMessageBox.warning(window, "Ошибка", "Не удалось получить информацию о лицензии")
            else:
                QMessageBox.warning(window, "Ошибка", "Лицензия недействительна")
        except (jwt.InvalidTokenError, requests.RequestException) as e:
            QMessageBox.warning(window, "Ошибка", f"Ошибка проверки лицензии: {e}")
    else:
        QMessageBox.warning(window, "Ошибка", "Лицензия не активирована")