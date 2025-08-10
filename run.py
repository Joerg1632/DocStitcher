import os
import sys
import threading
import multiprocessing
import jwt
import requests
from PyQt5.QtWidgets import (
    QApplication, QWidget, QFileDialog, QPushButton, QVBoxLayout, QListWidget,
    QListWidgetItem, QMessageBox, QSpacerItem, QSizePolicy, QHBoxLayout,
    QProgressBar, QCheckBox, QLabel, QComboBox, QDialog, QLineEdit,
    QToolButton, QMenu
)
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import QSettings, Qt, QTimer
from file_processing import save, save_as, convert_to_pdf, convert_doc_to_pdf, convert_image_to_pdf, update_progress, apply_scan_effect
from licensing import update_license_status, check_license_periodically, deactivate_device_action, \
    on_change_license_clicked, show_license_info
from client_utils import resource_path, get_device_id, verify_token, is_trial_valid, activate_license
from config import SERVER_URL, SECRET_KEY

white_list = ['.doc', '.docx', '.pdf', '.jpg', '.jpeg', '.png']

class WelcomeDialog(QDialog):
    def __init__(self, settings, device_id):
        super().__init__()
        self.settings = settings
        self.device_id = device_id
        self.setWindowTitle("DocStitcher")
        self.setWindowIcon(QIcon(resource_path("assets/app_icon.png")))
        self.setFixedSize(460, 260)
        self.setStyleSheet("""
            QLabel#subtitle {
                color: #666666;
                font-size: 12px;
            }
            QLineEdit {
                padding: 8px;
                font-size: 14px;
                border: 1px solid #cccccc;
                border-radius: 4px;
            }
            QPushButton {
                padding: 8px 14px;
                font-size: 13px;
                background-color: #5a84b0;
                color: white;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #4a70a0;
            }
        """)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)
        title = QLabel("Активация DocStitcher")
        title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("Введите лицензионный ключ или активируйте пробный период")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)
        main_layout.addWidget(subtitle)
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Ключ активации")
        self.key_input.setFixedWidth(300)
        self.key_input.setAlignment(Qt.AlignLeft)
        input_layout = QHBoxLayout()
        input_layout.addStretch()
        input_layout.addWidget(self.key_input)
        input_layout.addStretch()
        main_layout.addLayout(input_layout)
        main_layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
        button_layout = QHBoxLayout()
        trial_button = QPushButton("Пробный период (2 дня)")
        trial_button.clicked.connect(self.start_trial)
        activate_button = QPushButton("Активировать лицензию")
        activate_button.clicked.connect(self.activate_license)
        button_layout.addStretch()
        button_layout.addWidget(trial_button)
        button_layout.addSpacing(20)
        button_layout.addWidget(activate_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

    def showEvent(self, event):
        super().showEvent(event)
        self.key_input.setFocus(Qt.OtherFocusReason)

    def start_trial(self):
        try:
            response = requests.post(
                f"{SERVER_URL}/activate_trial",
                data={"device_id": self.device_id},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10
            )
            if response.status_code == 200:
                token = response.json()["access_token"]
                self.settings.setValue("license_token", token)
                self.accept()
            else:
                error_detail = response.json().get("detail", "Ошибка активации пробного периода")
                QMessageBox.critical(self, "Ошибка", f"Не удалось активировать пробный период: {error_detail}")
        except requests.RequestException as e:
            QMessageBox.critical(self, "Ошибка", f"Сервер недоступен или произошла ошибка соединения: {str(e)}")

    def activate_license(self):
        license_key = self.key_input.text().strip()
        if license_key:
            token = activate_license(license_key, self.device_id)
            if token:
                self.settings.setValue("license_token", token)
                self.accept()
        else:
            QMessageBox.critical(self, "Ошибка", "Лицензионный ключ не введён")

class MyWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.file_name_lst = []
        self.file_path = ""
        self.file_lst = []
        self.temp_file_path = []
        self.pdf_lst = []
        self.first_page_count = 0
        self.progress_lock = threading.Lock()
        self.temp_file_lock = threading.Lock()
        self.license_status = "Не активировано"
        self.progress_count = 0
        self.initUI()

    def initUI(self):
        self.setWindowTitle("DocStitcher (Не активировано)")
        self.setWindowIcon(QIcon(resource_path("assets/app_icon.png")))
        self.setGeometry(100, 100, 450, 300)

        license_button = QToolButton(self)
        license_button.setText("Лицензия")
        license_button.setToolTip("Взаимодействие с лицензией")

        license_button.setPopupMode(QToolButton.InstantPopup)
        license_button.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                color: #444;
                font-size: 11px;
                padding: 0px 0px;
                border: 1px solid #bbb;
                border-radius: 3px;
                min-height: 15px;
                min-width: 37px;
                margin-top: -4px;
            }
            QToolButton:hover {
                background-color: #f0f0f0;
            }
            QToolButton::menu-indicator {
                image: none;
            }
        """)
        license_menu = QMenu(license_button)
        license_menu.setToolTipsVisible(True)

        self.change_license_action = license_menu.addAction("Сменить лицензию")
        self.deactivate_action = license_menu.addAction("Деактивировать устройство")
        self.show_license_info_action = license_menu.addAction("Тип лицензии")
        license_button.setMenu(license_menu)
        self.change_license_action.setToolTip("Сменить лицензию группы устройств на другую")
        self.deactivate_action.setToolTip("Деактивировать лицензию на текущем устройстве и освободить место лицензии")
        self.show_license_info_action.setToolTip("Получить информацию о лицензии на этом устройстве")

        self.deactivate_action.triggered.connect(self.deactivate_device_action)
        self.change_license_action.triggered.connect(self.on_change_license_clicked)
        self.show_license_info_action.triggered.connect(self.show_license_info)
        self.list_widget = DragDropListWidget(self)
        self.list_widget.setDragDropMode(QListWidget.InternalMove)
        self.list_widget.setAcceptDrops(True)
        self.button1 = QPushButton("Выбрать файлы", self)
        self.button1.clicked.connect(self.get_directory)
        self.button3 = QPushButton("Очистить список", self)
        self.button3.clicked.connect(self.clear)
        self.button4 = QPushButton("Удалить выбранные", self)
        self.button4.clicked.connect(self.remove_selected_item)
        self.button5 = QPushButton("Объединить и сохранить", self)
        self.button5.setToolTip("Файл будет сохранён в папке 'Итоговые документы' рядом с программой")
        self.button5.clicked.connect(self.save)
        self.button6 = QPushButton("Объединить и сохранить как", self)
        self.button6.setToolTip("Ручной выбор местоположения и имени файла при сохранении итогового документа")
        self.button6.clicked.connect(self.save_as)
        self.checkbox_bw_first = QCheckBox("Перевести оригинал в Ч/Б", self)
        self.checkbox_bw_first.setChecked(False)
        self.ribbon_position_label = QLabel("Расположение ленты:", self)
        self.ribbon_position = QComboBox(self)
        self.ribbon_position.addItems(["Сверху", "Слева", "По середине"])
        self.ribbon_position.setCurrentIndex(0)
        save_layout = QHBoxLayout()
        save_layout.addWidget(self.button5)
        save_layout.addWidget(self.button6)
        save_layout.setSpacing(0)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        main_layout = QVBoxLayout()
        top_layout = QHBoxLayout()
        top_layout.addWidget(license_button)
        top_layout.addStretch()
        top_layout.setContentsMargins(0, 0, 0, 4)
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.button1)
        main_layout.addLayout(save_layout)
        main_layout.addWidget(self.button3)
        main_layout.addWidget(self.button4)
        main_layout.addWidget(self.list_widget)
        main_layout.addWidget(self.progress_bar)
        main_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))
        checkbox_layout = QHBoxLayout()
        checkbox_layout.addStretch()
        checkbox_layout.addWidget(self.checkbox_bw_first)
        checkbox_layout.addSpacing(20)
        checkbox_layout.addWidget(self.ribbon_position_label)
        checkbox_layout.addWidget(self.ribbon_position)
        checkbox_layout.addStretch()
        main_layout.addLayout(checkbox_layout)
        self.setLayout(main_layout)
        self.update_license_status()

        self.license_timer = QTimer(self)
        self.license_timer.timeout.connect(self.check_license_periodically)
        self.license_timer.start(300000)

        self.update_action_states()

    def get_directory(self):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        file_dialog = QFileDialog()
        file_dialog.setOptions(options)
        file_dialog.setFileMode(QFileDialog.ExistingFiles)
        file_dialog.setViewMode(QFileDialog.Detail)
        if file_dialog.exec_() == QFileDialog.Accepted:
            for file_path in file_dialog.selectedFiles():
                if not file_path.lower().endswith(tuple(white_list)):
                    print(f"[!] Неподдерживаемый формат файла: {file_path}")
                    continue
                normalized_path = os.path.normpath(file_path)
                if os.path.exists(normalized_path):
                    self.file_name_lst.append(os.path.basename(normalized_path))
                    self.file_lst.append(normalized_path)
                    item = QListWidgetItem(os.path.basename(normalized_path))
                    self.list_widget.addItem(item)
                else:
                    print(f"[!] Файл не найден: {normalized_path}")
            self.file_path = os.path.dirname(self.file_lst[0]) if self.file_lst else ""
            print(f"[+] {len(self.file_lst)} файл(ов) найден(о)!")

    def clear(self):
        self.list_widget.clear()
        self.file_name_lst.clear()
        self.file_lst.clear()
        self.temp_file_path.clear()
        self.progress_bar.setVisible(False)
        print("[*] Очистка списка файлов")

    def remove_selected_item(self):
        selected_items = self.list_widget.selectedItems()
        for item in selected_items:
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
            if row < len(self.file_name_lst):
                self.file_name_lst.pop(row)
                self.file_lst.pop(row)
        print(f"[*] Удалено {len(selected_items)} выбранных файлов")

    # Delegate methods to licensing module
    def update_license_status(self):
        update_license_status(self)

    def check_license_periodically(self):
        check_license_periodically(self)

    def deactivate_device_action(self):
        deactivate_device_action(self)

    def on_change_license_clicked(self):
        on_change_license_clicked(self)

    def show_license_info(self):
        show_license_info(self)

    def update_action_states(self):
        # This could also be moved to licensing.py if needed
        settings = QSettings("YourCompany", "DocStitcher")
        license_token = settings.value("license_token")
        if license_token:
            try:
                response = requests.get(f"{SERVER_URL}/verify",
                                        headers={"Authorization": f"Bearer {license_token}"})
                if response.status_code == 200:
                    payload = jwt.decode(license_token, SECRET_KEY,
                                        algorithms=["HS256"], options={"verify_exp": False})
                    license_id = payload.get("license_id")
                    license_response = requests.get(f"{SERVER_URL}/license/{license_id}",
                                                   headers={"Authorization": f"Bearer {license_token}"})
                    if license_response.status_code == 200:
                        license_data = license_response.json()
                        license_type = license_data.get("license_type_code", "")
                        self.deactivate_action.setEnabled(license_type != "LICENSE-TRIAL")
                    else:
                        self.deactivate_action.setEnabled(False)
                        self.change_license_action.setEnabled(False)
                else:
                    self.deactivate_action.setEnabled(False)
                    self.change_license_action.setEnabled(False)
            except (jwt.InvalidTokenError, requests.RequestException):
                self.deactivate_action.setEnabled(False)
                self.change_license_action.setEnabled(False)
        else:
            self.deactivate_action.setEnabled(False)
            self.change_license_action.setEnabled(False)

    def save(self):
        save(self)

    def save_as(self):
        save_as(self)

    def convert_to_pdf(self, doc_file):
        return convert_to_pdf(self, doc_file)

    def convert_doc_to_pdf(self, doc_file):
        return convert_doc_to_pdf(self, doc_file)

    def convert_image_to_pdf(self, image_file):
        return convert_image_to_pdf(self, image_file)

    def update_progress(self, value, total):
        update_progress(self, value, total)

    def apply_scan_effect(self, pdf_path, output_pdf=None):
        return apply_scan_effect(self, pdf_path, output_pdf)

class DragDropListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.InternalMove)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.source() == self:
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.source() == self:
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path.lower().endswith(tuple(white_list)):
                    item = QListWidgetItem(os.path.basename(file_path))
                    self.addItem(item)
                    self.parent().file_lst.append(file_path)
                    self.parent().file_name_lst.append(os.path.basename(file_path))
            event.accept()
        else:
            super().dropEvent(event)
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self.update_parent_lists)

    def update_parent_lists(self):
        new_file_lst = []
        new_name_lst = []
        for i in range(self.count()):
            item = self.item(i)
            name = item.text()
            try:
                idx = self.parent().file_name_lst.index(name)
                new_file_lst.append(self.parent().file_lst[idx])
                new_name_lst.append(name)
            except ValueError:
                pass
        self.parent().file_lst = new_file_lst
        self.parent().file_name_lst = new_name_lst
        print("[*] Обновлен порядок файлов после перемещения внутри списка")


if __name__ == '__main__':
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    settings = QSettings("YourCompany", "DocStitcher")
    device_id = get_device_id()
    license_token = settings.value("license_token")
    if license_token and verify_token(license_token, settings):
        mainWin = MyWindow()
        mainWin.show()
    elif is_trial_valid(settings):
        mainWin = MyWindow()
        mainWin.show()
    else:
        welcome_dialog = WelcomeDialog(settings, device_id)
        if welcome_dialog.exec_() == QDialog.Accepted:
            mainWin = MyWindow()
            mainWin.show()
        else:
            sys.exit(0)
    sys.exit(app.exec_())