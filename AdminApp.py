from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QComboBox, QLabel, QMessageBox, QLineEdit
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt, QTimer
import sys
import requests
from uuid import uuid4
import pyperclip
import os

SERVER_URL = "http://localhost:8000"

def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath("")
    return os.path.join(base_path, relative_path)

class AdminApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DocStitcher Admin")
        self.setWindowIcon(QIcon(resource_path("assets/app_icon.png")))
        self.setGeometry(100, 100, 500, 300)
        self.setMinimumSize(400, 250)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title_label = QLabel("Генерация лицензионных ключей")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        license_label = QLabel("Тип лицензии:")
        license_label.setFont(QFont("Arial", 12))
        layout.addWidget(license_label)
        self.license_type = QComboBox()
        self.license_type.setFont(QFont("Arial", 11))
        layout.addWidget(self.license_type)

        self.create_license_btn = QPushButton("Создать лицензию")
        self.create_license_btn.setFont(QFont("Arial", 12))
        self.create_license_btn.clicked.connect(self.create_license)
        layout.addWidget(self.create_license_btn)

        self.copy_btn = QPushButton("Копировать ключ")
        self.copy_btn.setFont(QFont("Arial", 12))
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        self.copy_btn.setEnabled(False)
        layout.addWidget(self.copy_btn)

        self.result_label = QLineEdit()
        self.result_label.setFont(QFont("Arial", 11))
        self.result_label.setReadOnly(True)
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setText("Ключ появится здесь после создания")
        layout.addWidget(self.result_label)

        layout.addStretch()

        self.central_widget.setLayout(layout)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QLabel {
                color: #333;
            }
            QComboBox {
                padding: 8px;
                border: 1px solid #ccc;
                border-radius: 5px;
                background-color: #fff;
                font-size: 14px;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: url(:/arrow-down.png);
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 10px;
                border: none;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QPushButton#copy_btn {
                background-color: #2196F3;
            }
            QPushButton#copy_btn:hover {
                background-color: #1e87db;
            }
            QLineEdit {
                padding: 8px;
                border: 1px solid #ccc;
                border-radius: 5px;
                background-color: #fff;
                color: #333;
                font-size: 14px;
                text-align: center;
            }
            QLineEdit:read-only {
                background-color: #f0f0f0;
                border: 1px solid #bbb;
            }
        """)

        self.last_license_key = ""

        self.code_to_name = {
            "LICENSE-1": "Лицензия на 1 устройство",
            "LICENSE-5": "Лицензия на 5 устройств",
            "LICENSE-15": "Лицензия на 15 устройств",
            "LICENSE-UNLIMITED": "Лицензия без ограничений"
        }
        self.load_license_types()

    def load_license_types(self):
        try:
            response = requests.get(f"{SERVER_URL}/license_types", timeout=5)
            if response.status_code == 200:
                license_types = response.json()
                self.license_type.clear()
                for lt in license_types:
                    code = lt["code"]
                    if code in self.code_to_name and code != "LICENSE-TRIAL":
                        self.license_type.addItem(self.code_to_name[code])
            else:
                self.result_label.setText(f"Ошибка: Сервер вернул код {response.status_code}. Используются стандартные типы.")
                self.result_label.setStyleSheet("color: #d32f2f;")
                QMessageBox.warning(self, "Предупреждение", f"Сервер вернул код {response.status_code}. Используются стандартные типы.")
                self.load_default_license_types()
        except requests.exceptions.ConnectionError as e:
            self.result_label.setText(f"Ошибка соединения: {str(e)}. Используются стандартные типы.")
            self.result_label.setStyleSheet("color: #d32f2f;")
            QMessageBox.warning(self, "Предупреждение", f"Ошибка соединения: {str(e)}. Используются стандартные типы.")
            self.load_default_license_types()
        except requests.exceptions.Timeout:
            self.result_label.setText("Тайм-аут соединения. Используются стандартные типы.")
            self.result_label.setStyleSheet("color: #d32f2f;")
            QMessageBox.warning(self, "Предупреждение", "Тайм-аут соединения. Используются стандартные типы.")
            self.load_default_license_types()
        except Exception as e:
            self.result_label.setText(f"Неизвестная ошибка: {str(e)}. Используются стандартные типы.")
            self.result_label.setStyleSheet("color: #d32f2f;")
            QMessageBox.warning(self, "Предупреждение", f"Неизвестная ошибка: {str(e)}. Используются стандартные типы.")
            self.load_default_license_types()

    def load_default_license_types(self):
        self.license_type.clear()
        for name in self.code_to_name.values():
            self.license_type.addItem(name)

    def create_license(self):
        license_name = self.license_type.currentText()
        license_code = next(code for code, name in self.code_to_name.items() if name == license_name)
        if not license_code:
            self.result_label.setText("Ошибка: выберите тип лицензии")
            self.result_label.setStyleSheet("color: #d32f2f;")
            QMessageBox.critical(self, "Ошибка", "Выберите тип лицензии")
            return

        license_key = str(uuid4())
        try:
            response = requests.post(f"{SERVER_URL}/create_license", json={
                "license_type_code": license_code,
                "license_key": license_key
            }, timeout=5)
            if response.status_code == 200:
                license_key = response.json().get("license_key", "Неизвестный ключ")
                self.last_license_key = license_key
                self.result_label.setText(f"Лицензия создана: {license_key}")
                self.result_label.setStyleSheet("color: #2e7d32;")
                self.copy_btn.setEnabled(True)
                QMessageBox.information(self, "Успех", f"Лицензия создана: {license_key}\nНажмите 'Копировать ключ' или скопируйте вручную")
            else:
                error = response.json().get("detail", "Ошибка создания лицензии")
                self.result_label.setText(f"Ошибка: {error}")
                self.result_label.setStyleSheet("color: #d32f2f;")
                self.copy_btn.setEnabled(False)
                QMessageBox.critical(self, "Ошибка", f"Ошибка: {error}")
        except requests.exceptions.ConnectionError as e:
            self.result_label.setText(f"Ошибка соединения: {str(e)}")
            self.result_label.setStyleSheet("color: #d32f2f;")
            self.copy_btn.setEnabled(False)
            QMessageBox.critical(self, "Ошибка", f"Ошибка соединения: {str(e)}")
        except requests.exceptions.Timeout:
            self.result_label.setText("Тайм-аут при создании лицензии")
            self.result_label.setStyleSheet("color: #d32f2f;")
            self.copy_btn.setEnabled(False)
            QMessageBox.critical(self, "Ошибка", "Тайм-аут при создании лицензии")
        except Exception as e:
            self.result_label.setText(f"Неизвестная ошибка: {str(e)}")
            self.result_label.setStyleSheet("color: #d32f2f;")
            self.copy_btn.setEnabled(False)
            QMessageBox.critical(self, "Ошибка", f"Неизвестная ошибка: {str(e)}")

    def copy_to_clipboard(self):
        if self.last_license_key:
            pyperclip.copy(self.last_license_key)
            self.result_label.setText(f"Ключ скопирован в буфер обмена!")
            self.result_label.setStyleSheet("color: #2e7d32;")
            QTimer.singleShot(2000, lambda: self.result_label.setText(f"Лицензия создана: {self.last_license_key}"))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    admin = AdminApp()
    admin.show()
    sys.exit(app.exec_())