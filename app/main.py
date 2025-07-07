import os
import sys
from PIL import ImageEnhance, Image
import random
import pymupdf as fitz
import win32com.client
from PyPDF2 import PdfMerger
from PyQt5.QtWidgets import QApplication, QWidget, QFileDialog, QPushButton, QVBoxLayout, QListWidget, QListWidgetItem, \
    QMessageBox, QSpacerItem, QSizePolicy, QHBoxLayout, QProgressBar, QCheckBox
from PyQt5.QtGui import QIcon
import img2pdf
import shutil
import tempfile
import time
from PyQt5.QtCore import QTimer

white_list = ['.doc', '.docx', '.pdf', '.jpg', '.jpeg', '.png']

def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath("..")
    return os.path.join(base_path, relative_path)

class MyWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.file_name_lst = []
        self.file_path = ""
        self.file_lst = []
        self.temp_file_path = []
        self.pdf_lst = []
        self.first_page_count = 0

        self.initUI()

    def initUI(self):
        self.setWindowTitle("Объединение документов")
        self.setWindowIcon(QIcon(resource_path("../assets/app_icon.png")))
        self.setGeometry(100, 100, 400, 300)

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
        self.button5.clicked.connect(self.save)

        self.button6 = QPushButton("Объединить и сохранить как", self)
        self.button6.clicked.connect(self.save_as)

        self.checkbox_bw_first = QCheckBox("Перевести оригинал в Ч/Б", self)
        self.checkbox_bw_first.setChecked(False)

        save_layout = QHBoxLayout()
        save_layout.addWidget(self.button5)
        save_layout.addWidget(self.button6)
        save_layout.setSpacing(0)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)

        layout = QVBoxLayout()
        layout.addWidget(self.button1)
        layout.addLayout(save_layout)
        layout.addWidget(self.button3)
        layout.addWidget(self.button4)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.progress_bar)
        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))
        layout.addWidget(self.checkbox_bw_first)
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)

    def update_progress(self, value, total):
        self.progress_bar.setVisible(True)
        percent = int((value / total) * 100)
        self.progress_bar.setValue(percent)
        QApplication.processEvents()

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

    def apply_scan_effect(self, pdf_path, output_pdf=None):
        if output_pdf is None:
            output_pdf = pdf_path
        try:
            dpi = 100
            pt_to_px = lambda pt: int(pt * dpi / 72)

            a4_width_pt = 595
            a4_height_pt = 842
            a4_width_px = pt_to_px(a4_width_pt)
            a4_height_px = pt_to_px(a4_height_pt)

            doc = fitz.open(pdf_path)
            new_doc = fitz.open()

            ribbon_path = resource_path("../assets/ribbon.png")
            dot1_path = resource_path("../assets/dot1.png")
            dot2_path = resource_path("../assets/dot2.png")

            for page_num in range(len(doc) - 1):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(alpha=False, dpi=dpi)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                if page_num < self.first_page_count and self.checkbox_bw_first.isChecked():
                    img = img.convert("L")

                margin_px = pt_to_px(10)
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

                if page_num == 0 and os.path.exists(ribbon_path):
                    ribbon = Image.open(ribbon_path).convert("RGBA")
                    ribbon_scale = 0.35 * (a4_width_pt / 595)
                    ribbon_width = int(ribbon.width * ribbon_scale)
                    ribbon_height = int(ribbon.height * ribbon_scale)
                    ribbon_resized = ribbon.resize((ribbon_width, ribbon_height), Image.Resampling.LANCZOS)
                    ribbon_x = pt_to_px(a4_width_pt - ribbon_width - 490)
                    ribbon_y = pt_to_px(11)
                    new_img.paste(ribbon_resized, (ribbon_x, ribbon_y), ribbon_resized)

                elif os.path.exists(dot1_path) and os.path.exists(dot2_path):
                    dot_file = random.choice([dot1_path, dot2_path])
                    dot = Image.open(dot_file).convert("RGBA")
                    dot = dot.resize((pt_to_px(19), pt_to_px(18)), Image.Resampling.LANCZOS)
                    new_img.paste(dot, (pt_to_px(72), pt_to_px(44)), dot)

                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                    temp_img_path = tmpfile.name
                    new_img.save(temp_img_path, "PNG", dpi=(dpi, dpi))

                new_page = new_doc.new_page(width=a4_width_pt, height=a4_height_pt)

                img_width_pt = new_width * 72 / dpi
                img_height_pt = new_height * 72 / dpi
                x_pt = x_offset * 72 / dpi
                y_pt = y_offset * 72 / dpi
                rect = fitz.Rect(x_pt, y_pt, x_pt + img_width_pt, y_pt + img_height_pt)

                new_page.insert_image(rect, filename=temp_img_path)
                os.remove(temp_img_path)

            if len(doc) > 0:
                new_doc.insert_pdf(doc, from_page=len(doc) - 1, to_page=len(doc) - 1)

            temp_output = output_pdf + ".tmp"
            new_doc.save(temp_output)
            new_doc.close()
            doc.close()
            time.sleep(0.3)

            if os.path.exists(output_pdf):
                try:
                    os.remove(output_pdf)
                except Exception as e:
                    print(f"[!] Не удалось удалить старый файл: {e}")
            os.replace(temp_output, output_pdf)
            return output_pdf

        except Exception as e:
            print(f"[!] Ошибка при создании эффекта сканирования: {e}")
            return pdf_path

    def save(self):
        if not self.file_lst:
            QMessageBox.warning(self, "Ошибка", "Нет файлов для объединения!")
            return

        pdf_lst = [None] * len(self.file_lst)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        for i, file_path in enumerate(self.file_lst):
            ext = file_path.lower().rsplit('.', 1)[-1]

            if ext == 'docx':
                pdf_path = self.convert_to_pdf(file_path)
            elif ext == 'doc':
                pdf_path = self.convert_doc_to_pdf(file_path)
            elif ext == 'pdf':
                pdf_path = self.normalize_pdf_size(file_path)
            elif ext in ('jpg', 'jpeg', 'png'):
                pdf_path = self.convert_image_to_pdf(file_path)
            else:
                pdf_path = None
                print(f"[!] Неподдерживаемый формат файла: {file_path}")

            if pdf_path and os.path.exists(pdf_path):
                pdf_lst[i] = pdf_path
            else:
                print(f"[!] Не удалось обработать: {file_path}")

            self.update_progress(i + 1, len(self.file_lst))

        pdf_lst = [p for p in pdf_lst if p is not None and os.path.exists(p)]
        if not pdf_lst:
            QMessageBox.warning(self, "Ошибка", "Не удалось преобразовать файлы!")
            self.progress_bar.setVisible(False)
            return

        first_pdf_path = pdf_lst[0]
        doc_first = fitz.open(first_pdf_path)
        self.first_page_count = len(doc_first)
        doc_first.close()

        pdf_merger = PdfMerger()
        for pdf_file in pdf_lst:
            try:
                pdf_merger.append(pdf_file)
            except Exception as e:
                print(f"[!] Ошибка при добавлении {pdf_file}: {e}")

        app_dir = os.path.dirname(sys.argv[0])
        output_dir = os.path.join(app_dir, "MergedPDFs")
        os.makedirs(output_dir, exist_ok=True)
        base_name = "merged_document"
        output_file = os.path.join(output_dir, f"{base_name}.pdf")
        counter = 1
        while os.path.exists(output_file):
            output_file = os.path.join(output_dir, f"{base_name}{counter}.pdf")
            counter += 1
        try:
            pdf_merger.write(output_file)
            pdf_merger.close()
            self.apply_scan_effect(output_file)
            for file_path in self.temp_file_path:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        print(f"[!] Ошибка при удалении временного файла {file_path}: {e}")
            self.temp_file_path = []
            QMessageBox.information(self, "Успешно", f"Файлы объединены и сохранены в:\n{output_file}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл: {e}")
            print(f"[!] Ошибка сохранения: {e}")
        finally:
            self.progress_bar.setVisible(False)

    def save_as(self):
        if not self.file_lst:
            QMessageBox.warning(self, "Ошибка", "Нет файлов для объединения!")
            return

        pdf_lst = [None] * len(self.file_lst)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        for i, file_path in enumerate(self.file_lst):
            ext = file_path.lower().rsplit('.', 1)[-1]

            if ext == 'docx':
                pdf_path = self.convert_to_pdf(file_path)
            elif ext == 'doc':
                pdf_path = self.convert_doc_to_pdf(file_path)
            elif ext == 'pdf':
                pdf_path = self.normalize_pdf_size(file_path)
            elif ext in ('jpg', 'jpeg', 'png'):
                pdf_path = self.convert_image_to_pdf(file_path)
            else:
                pdf_path = None
                print(f"[!] Неподдерживаемый формат файла: {file_path}")

            if pdf_path and os.path.exists(pdf_path):
                pdf_lst[i] = pdf_path
            else:
                print(f"[!] Не удалось обработать: {file_path}")

            self.update_progress(i + 1, len(self.file_lst))

        pdf_lst = [p for p in pdf_lst if p is not None and os.path.exists(p)]
        if not pdf_lst:
            QMessageBox.warning(self, "Ошибка", "Не удалось преобразовать файлы!")
            self.progress_bar.setVisible(False)
            return

        first_pdf_path = pdf_lst[0]
        doc_first = fitz.open(first_pdf_path)
        self.first_page_count = len(doc_first)
        doc_first.close()

        pdf_merger = PdfMerger()
        for pdf_file in pdf_lst:
            try:
                pdf_merger.append(pdf_file)
            except Exception as e:
                print(f"[!] Ошибка при добавлении {pdf_file}: {e}")

        output_file = \
            QFileDialog.getSaveFileName(self, "Сохранить объединенный PDF", self.file_path, "PDF Files (*.pdf)")[0]
        if output_file:
            try:
                pdf_merger.write(output_file)
                pdf_merger.close()
                self.apply_scan_effect(output_file)
                for file_path in self.temp_file_path:
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            print(f"[!] Ошибка при удалении временного файла {file_path}: {e}")
                self.temp_file_path = []
                QMessageBox.information(self, "Успешно", f"Файлы объединены и сохранены в:\n{output_file}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл: {e}")
                print(f"[!] Ошибка сохранения: {e}")
            finally:
                self.progress_bar.setVisible(False)

    def normalize_pdf_size(self, pdf_file):
        try:
            doc = fitz.open(pdf_file)
            if len(doc) == 0:
                return None

            output_pdf = pdf_file.replace('.pdf', '_normalized.pdf')
            new_doc = fitz.open()
            a4_width = 595
            a4_height = 842

            for page in doc:
                new_page = new_doc.new_page(width=a4_width, height=a4_height)
                new_page.show_pdf_page(new_page.rect, doc, page.number)
            new_doc.save(output_pdf)
            new_doc.close()
            doc.close()
            self.temp_file_path.append(output_pdf)
            return output_pdf
        except Exception as e:
            print(f"[!] Ошибка нормализации PDF: {e}")
            return None

    def convert_to_pdf(self, doc_file):

        try:
            if not os.path.exists(doc_file):
                print(f"[!] Файл не найден для конвертации: {doc_file}")
                return None

            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                temp_docx_path = tmp.name
            shutil.copyfile(doc_file, temp_docx_path)

            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0

            doc = word.Documents.Open(os.path.abspath(temp_docx_path))
            temp_pdf = temp_docx_path.replace('.docx', '.pdf')
            doc.SaveAs(temp_pdf, FileFormat=17)
            doc.Close()
            word.Quit()

            self.temp_file_path.append(temp_pdf)
            os.remove(temp_docx_path)

            normalized_pdf = self.normalize_pdf_size(temp_pdf)
            if normalized_pdf:
                self.temp_file_path.append(normalized_pdf)
                os.remove(temp_pdf)
                print(f"[+] Конвертирован и нормализован {doc_file} в {normalized_pdf}")
                return normalized_pdf
            return None

        except Exception as e:
            print(f"[!] Ошибка при конвертации .docx в PDF: {e}")
            return None

    def convert_doc_to_pdf(self, doc_file):
        pdf_file = doc_file.replace('.doc', '_normalized.pdf')
        try:
            if os.path.exists(doc_file):
                word = win32com.client.Dispatch("Word.Application")
                word.Visible = False
                doc = word.Documents.Open(os.path.normpath(doc_file))
                temp_pdf = doc_file.replace('.doc', '.pdf')
                doc.SaveAs(temp_pdf, FileFormat=17)
                doc.Close()
                word.Quit()
                self.temp_file_path.append(temp_pdf)
                normalized_pdf = self.normalize_pdf_size(temp_pdf)
                if normalized_pdf:
                    self.temp_file_path.append(normalized_pdf)
                    os.remove(temp_pdf)
                    print(f"[+] Конвертирован и нормализован {doc_file} в {normalized_pdf}")
                    return normalized_pdf
                return None
            else:
                print(f"[!] Файл не найден для конвертации: {doc_file}")
                return None
        except Exception as e:
            print(f"[!] Ошибка при конвертации .doc в PDF: {e}")
            return None

    def convert_image_to_pdf(self, image_file):
        """
        Новая функция для конвертации изображения через img2pdf под формат A4 без потерь.
        """
        try:
            if not os.path.exists(image_file):
                print(f"[!] Файл не найден для конвертации: {image_file}")
                return None

            pdf_file = os.path.splitext(image_file)[0] + '_img2pdf.pdf'

            a4_page_size = [img2pdf.in_to_pt(8.3), img2pdf.in_to_pt(11.7)]
            layout_fun = img2pdf.get_layout_fun(a4_page_size)

            with open(pdf_file, "wb") as f:
                f.write(img2pdf.convert(image_file, layout_fun=layout_fun))

            print(f"[+] Конвертирован {image_file} в PDF через img2pdf: {pdf_file}")
            self.temp_file_path.append(pdf_file)
            return pdf_file

        except Exception as e:
            print(f"[!] Ошибка при конвертации {image_file} в PDF через img2pdf: {e}")
            return None

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
    app = QApplication(sys.argv)
    mainWin = MyWindow()
    mainWin.show()
    sys.exit(app.exec_())