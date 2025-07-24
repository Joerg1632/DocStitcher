import fitz  # PyMuPDF

# Открываем исходный документ
src_doc = fitz.open("Ivannikov Court Cases.pdf")
dst_doc = fitz.open()

for i in range(len(src_doc)):
    src_page = src_doc[i]

    # Создаём новую A4 страницу
    new_page = dst_doc.new_page(width=595.276, height=841.890)  # A4 в pt

    # Получаем размеры оригинальной страницы
    src_rect = src_page.rect
    dst_rect = new_page.rect

    # Считаем масштаб и вписываем содержимое
    src_ratio = src_rect.width / src_rect.height
    dst_ratio = dst_rect.width / dst_rect.height

    if src_ratio > dst_ratio:
        new_width = dst_rect.width
        new_height = new_width / src_ratio
    else:
        new_height = dst_rect.height
        new_width = new_height * src_ratio

    x0 = (dst_rect.width - new_width) / 2
    y0 = (dst_rect.height - new_height) / 2
    x1 = x0 + new_width
    y1 = y0 + new_height

    target_rect = fitz.Rect(x0, y0, x1, y1)

    # Вставляем содержимое исходной страницы
    new_page.show_pdf_page(target_rect, src_doc, i)

# Сохраняем
dst_doc.save("output_fixed.pdf")
