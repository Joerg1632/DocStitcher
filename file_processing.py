import os
import sys
import tempfile
import time
from PyQt5.QtWidgets import QMessageBox, QFileDialog
from PyPDF2 import PdfMerger
import pymupdf as fitz
import comtypes.client
from multiprocessing import Pool
import pythoncom
from docx2pdf import convert
import img2pdf

from client_utils import pt_to_px, resource_path, get_max_workers, process_page

white_list = ['.doc', '.docx', '.pdf', '.jpg', '.jpeg', '.png']

def update_progress(window, value, total):
    window.progress_bar.setVisible(True)
    percent = int((value / total) * 100)
    window.progress_bar.setValue(percent)
    from PyQt5.QtWidgets import QApplication
    QApplication.processEvents()

def convert_to_pdf(window, doc_file):
    if not os.path.exists(doc_file):
        print(f"[!] Файл не найден для конвертации: {doc_file}")
        return None
    if not doc_file.lower().endswith(".docx"):
        print(f"[!] Недопустимый тип файла для convert_to_pdf: {doc_file}")
        return None
    temp_name = next(tempfile._get_candidate_names()) + '.pdf'
    temp_pdf = os.path.join(tempfile.gettempdir(), temp_name)
    try:
        convert(input_path=doc_file, output_path=temp_pdf)
        print(f"[+] Конвертировано через docx2pdf: {doc_file}")
    except Exception as e:
        print(f"[!] Ошибка в docx2pdf: {e}")
        try:
            pythoncom.CoInitialize()
            wdFormatPDF = 17
            word = comtypes.client.CreateObject('Word.Application')
            time.sleep(1.2)
            word.Visible = False
            word.DisplayAlerts = 0
            doc = word.Documents.Open(os.path.abspath(doc_file))
            doc.SaveAs(temp_pdf, FileFormat=wdFormatPDF)
            doc.Close(False)
            word.Quit()
            print(f"[+] Конвертировано через comtypes: {doc_file}")
        except Exception as e:
            print(f"[!] Fallback через comtypes не сработал: {e}")
            return None
        finally:
            if 'word' in locals():
                try:
                    word.Quit()
                except:
                    pass
            pythoncom.CoUninitialize()
    if os.path.exists(temp_pdf):
        window.temp_file_path.append(temp_pdf)
    return temp_pdf

def convert_doc_to_pdf(window, doc_file):
    if not os.path.exists(doc_file):
        print(f"[!] Файл не найден для конвертации: {doc_file}")
        return None
    try:
        pythoncom.CoInitialize()
        wdFormatPDF = 17
        temp_name = next(tempfile._get_candidate_names()) + '.pdf'
        temp_pdf = os.path.join(tempfile.gettempdir(), temp_name)
        word = comtypes.client.CreateObject('Word.Application')
        time.sleep(1.5)
        word.DisplayAlerts = 0
        print(f"[*] Открытие документа: {doc_file}")
        doc = word.Documents.Open(os.path.abspath(doc_file))
        doc.SaveAs(temp_pdf, FileFormat=wdFormatPDF)
        doc.Close(False)
        word.Quit()
        print(f"[+] Конвертировано .doc через comtypes: {doc_file}")
        if os.path.exists(temp_pdf):
            window.temp_file_path.append(temp_pdf)
        return temp_pdf
    except Exception as e:
        print(f"[!] Ошибка при конвертации .doc через comtypes: {e}")
        return None
    finally:
        if 'word' in locals():
            try:
                word.Quit()
            except:
                pass
        pythoncom.CoUninitialize()

def convert_image_to_pdf(window, image_file):
    try:
        if not os.path.exists(image_file):
            print(f"[!] Файл не найден для конвертации: {image_file}")
            return None
        temp_name = next(tempfile._get_candidate_names()) + '_img2pdf.pdf'
        pdf_file = os.path.join(tempfile.gettempdir(), temp_name)
        a4_page_size = [img2pdf.in_to_pt(8.25), img2pdf.in_to_pt(11.65)]
        layout_fun = img2pdf.get_layout_fun(a4_page_size)
        with open(pdf_file, "wb") as f:
            f.write(img2pdf.convert(image_file, layout_fun=layout_fun))
        print(f"[+] Конвертирован {image_file} в PDF через img2pdf: {pdf_file}")
        window.temp_file_path.append(pdf_file)
        return pdf_file
    except Exception as e:
        print(f"[!] Ошибка при конвертации {image_file} в PDF через img2pdf: {e}")
        return None

def save(window):
    if not window.file_lst:
        QMessageBox.warning(window, "Ошибка", "Нет файлов для объединения!")
        return
    pdf_lst = [None] * len(window.file_lst)
    window.progress_bar.setVisible(True)
    window.progress_bar.setValue(0)
    for i, file_path in enumerate(window.file_lst):
        ext = file_path.lower().rsplit('.', 1)[-1]
        if ext == 'docx':
            pdf_path = convert_to_pdf(window, file_path)
        elif ext == 'doc':
            pdf_path = convert_doc_to_pdf(window, file_path)
        elif ext == 'pdf':
            pdf_path = file_path
        elif ext in ('jpg', 'jpeg', 'png'):
            pdf_path = convert_image_to_pdf(window, file_path)
        else:
            pdf_path = None
            print(f"[!] Неподдерживаемый формат файла: {file_path}")
        if pdf_path and os.path.exists(pdf_path):
            pdf_lst[i] = pdf_path
        else:
            print(f"[!] Не удалось обработать: {file_path}")
        update_progress(window, i + 1, len(window.file_lst))
    pdf_lst = [p for p in pdf_lst if p is not None and os.path.exists(p)]
    if not pdf_lst:
        QMessageBox.warning(window, "Ошибка", "Не удалось преобразовать файлы!")
        window.progress_bar.setVisible(False)
        return
    first_pdf_path = pdf_lst[0]
    doc_first = fitz.open(first_pdf_path)
    window.first_page_count = len(doc_first)
    doc_first.close()
    pdf_merger = PdfMerger()
    for pdf_file in pdf_lst:
        try:
            pdf_merger.append(pdf_file)
        except Exception as e:
            print(f"[!] Ошибка при добавлении {pdf_file}: {e}")
    app_dir = os.path.dirname(sys.argv[0])
    output_dir = os.path.join(app_dir, "Итоговые документы")
    os.makedirs(output_dir, exist_ok=True)
    first_file_name = os.path.splitext(os.path.basename(window.file_lst[0]))[0]
    base_name = first_file_name
    window.output_file = os.path.join(output_dir, f"{base_name}.pdf")
    if os.path.exists(window.output_file):
        msg_box = QMessageBox(window)
        msg_box.setWindowTitle("Файл уже существует")
        msg_box.setText(f"Файл с именем '{base_name}.pdf' уже существует.\nПерезаписать его?")
        yes_button = msg_box.addButton("Да", QMessageBox.YesRole)
        no_button = msg_box.addButton("Нет", QMessageBox.NoRole)
        msg_box.exec_()
        if msg_box.clickedButton() == no_button:
            QMessageBox.information(window, "Отменено", "Сохранение отменено.")
            window.progress_bar.setVisible(False)
            return
    try:
        pdf_merger.write(window.output_file)
        pdf_merger.close()
        apply_scan_effect(window, window.output_file)
        for file_path in window.temp_file_path:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"[!] Ошибка при удалении временного файла {file_path}: {e}")
        window.temp_file_path = []
        QMessageBox.information(window, "Успешно", f"Файлы объединены и сохранены в:\n{window.output_file}")
    except Exception as e:
        QMessageBox.critical(window, "Ошибка", f"Не удалось сохранить файл: {e}")
        print(f"[!] Ошибка сохранения: {e}")
    finally:
        window.progress_bar.setVisible(False)

def save_as(window):
    if not window.file_lst:
        QMessageBox.warning(window, "Ошибка", "Нет файлов для объединения!")
        return
    pdf_lst = [None] * len(window.file_lst)
    window.progress_bar.setVisible(True)
    window.progress_bar.setValue(0)
    for i, file_path in enumerate(window.file_lst):
        ext = file_path.lower().rsplit('.', 1)[-1]
        if ext == 'docx':
            pdf_path = convert_to_pdf(window, file_path)
        elif ext == 'doc':
            pdf_path = convert_doc_to_pdf(window, file_path)
        elif ext == 'pdf':
            pdf_path = file_path
        elif ext in ('jpg', 'jpeg', 'png'):
            pdf_path = convert_image_to_pdf(window, file_path)
        else:
            pdf_path = None
            print(f"[!] Неподдерживаемый формат файла: {file_path}")
        if pdf_path and os.path.exists(pdf_path):
            pdf_lst[i] = pdf_path
        else:
            print(f"[!] Не удалось обработать: {file_path}")
        update_progress(window, i + 1, len(window.file_lst))
    pdf_lst = [p for p in pdf_lst if p is not None and os.path.exists(p)]
    if not pdf_lst:
        QMessageBox.warning(window, "Ошибка", "Не удалось преобразовать файлы!")
        window.progress_bar.setVisible(False)
        return
    first_pdf_path = pdf_lst[0]
    doc_first = fitz.open(first_pdf_path)
    window.first_page_count = len(doc_first)
    doc_first.close()
    pdf_merger = PdfMerger()
    for pdf_file in pdf_lst:
        try:
            pdf_merger.append(pdf_file)
        except Exception as e:
            print(f"[!] Ошибка при добавлении {pdf_file}: {e}")
    first_file_name = os.path.splitext(os.path.basename(window.file_lst[0]))[0]
    suggested_name = os.path.join(window.file_path, f"{first_file_name}.pdf")
    output_file, _ = QFileDialog.getSaveFileName(
        window, "Сохранить объединенный PDF", suggested_name, "PDF Files (*.pdf)"
    )
    if not output_file:
        QMessageBox.information(window, "Отменено", "Сохранение отменено.")
        window.progress_bar.setVisible(False)
        return
    if output_file:
        try:
            pdf_merger.write(output_file)
            pdf_merger.close()
            apply_scan_effect(window, output_file)
            for file_path in window.temp_file_path:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        print(f"[!] Ошибка при удалении временного файла {file_path}: {e}")
            window.temp_file_path = []
            QMessageBox.information(window, "Успешно", f"Файлы объединены и сохранены в:\n{output_file}")
        except Exception as e:
            QMessageBox.critical(window, "Ошибка", f"Не удалось сохранить файл: {e}")
            print(f"[!] Ошибка сохранения: {e}")
        finally:
            window.progress_bar.setVisible(False)

def apply_scan_effect(window, pdf_path, output_pdf=None):
    if output_pdf is None:
        output_pdf = pdf_path
    try:
        start_time = time.perf_counter()
        dpi = 210
        a4_width_pt = 595
        a4_height_pt = 842
        a4_width_px = pt_to_px(a4_width_pt, dpi)
        a4_height_px = pt_to_px(a4_height_pt, dpi)
        doc = fitz.open(pdf_path)
        new_doc = fitz.open()
        page_count = len(doc) - 1
        if page_count == 0:
            new_doc.insert_pdf(doc)
            new_doc.save(output_pdf)
            new_doc.close()
            doc.close()
            window.progress_bar.setVisible(False)
            return output_pdf
        window.progress_count = 0
        ribbon_path = resource_path("assets/ribbons/ribbon.png")
        ribbon_left_path = resource_path("assets/ribbons/ribbon_left.png")
        ribbon_middle_path = resource_path("assets/ribbons/ribbon_middle.png")
        dot1_path = resource_path("assets/dots/dot1.png")
        dot2_path = resource_path("assets/dots/dot2.png")
        dot_mid_path = resource_path("assets/dots/middle_dot.png")
        temp_images = [None] * page_count
        max_workers = get_max_workers(page_count)
        with Pool(processes=max_workers) as pool:
            results = [
                pool.apply_async(
                    process_page,
                    args=(
                        page_num,
                        pdf_path,
                        a4_width_px,
                        a4_height_px,
                        dpi,
                        window.ribbon_position.currentText(),
                        window.first_page_count,
                        window.checkbox_bw_first.isChecked(),
                        ribbon_path,
                        ribbon_left_path,
                        ribbon_middle_path,
                        dot1_path,
                        dot2_path,
                        dot_mid_path
                    )
                ) for page_num in range(page_count)
            ]
            for r in results:
                page_num, temp_img_path = r.get()
                window.progress_count += 1
                window.update_progress(window.progress_count, page_count)
                if temp_img_path:
                    temp_images[page_num] = temp_img_path
        for page_num in range(page_count):
            if temp_images[page_num]:
                new_page = new_doc.new_page(width=a4_width_pt, height=a4_height_pt)
                rect = fitz.Rect(0, 0, a4_width_pt, a4_height_pt)
                new_page.insert_image(rect, filename=temp_images[page_num])
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
        for temp_img_path in temp_images:
            if temp_img_path and os.path.exists(temp_img_path):
                try:
                    os.remove(temp_img_path)
                except Exception as e:
                    print(f"[!] Ошибка при удалении временного файла {temp_img_path}: {e}")
        window.temp_file_path = [f for f in window.temp_file_path if f not in temp_images]
        window.progress_bar.setVisible(False)
        return output_pdf
    except Exception as e:
        print(f"[!] Ошибка при создании эффекта сканирования: {e}")
        window.progress_bar.setVisible(False)
        return pdf_path