import os
import win32com.client

file_docx = r"C:\Users\yurav\Downloads\Telegram Desktop\test.docx"
file_pdf = file_docx.rsplit('.', 1)[0] + '.pdf'

try:
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = word.Documents.Open(os.path.abspath(file_docx))
    doc.SaveAs(file_pdf, FileFormat=17)
    doc.Close()
    print("Конвертация прошла успешно!")
except Exception as e:
    print("Ошибка:", e)
finally:
    word.Quit()
