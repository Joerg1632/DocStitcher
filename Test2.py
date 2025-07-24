import fitz
from PIL import Image
import os
import tempfile

def normalize_pdf_size(pdf_file):
    try:
        doc = fitz.open(pdf_file)
        if len(doc) == 0:
            return None, []

        temp_name = next(tempfile._get_candidate_names()) + '_normalized.pdf'
        output_pdf = os.path.join(tempfile.gettempdir(), temp_name)
        new_doc = fitz.open()
        a4_width = 595
        a4_height = 842
        margin_pt = 5
        page_info = []

        for page in doc:
            src_width = page.rect.width
            src_height = page.rect.height
            print(f"Original page size: {src_width} x {src_height} pt")
            scale = min((a4_width - 2 * margin_pt) / src_width, (a4_height - 2 * margin_pt) / src_height)
            new_width = src_width * scale
            new_height = src_height * scale
            x_offset = (a4_width - new_width) / 2
            y_offset = (a4_height - new_height) / 2
            new_page = new_doc.new_page(width=a4_width, height=a4_height)
            rect = fitz.Rect(x_offset, y_offset, x_offset + new_width, y_offset + new_height)
            new_page.show_pdf_page(rect, doc, page.number)
            page_info.append({
                'page_num': page.number,
                'x_offset': x_offset,
                'y_offset': y_offset,
                'width': new_width,
                'height': new_height
            })

        new_doc.save(output_pdf)
        new_doc.close()
        doc.close()
        for info in page_info:
            print(f"Page {info['page_num']}: x={info['x_offset']:.2f} pt, y={info['y_offset']:.2f} pt, "
                  f"w={info['width']:.2f} pt, h={info['height']:.2f} pt")
        return output_pdf, page_info

    except Exception as e:
        print(f"[!] Ошибка нормализации PDF: {e}")
        return None, []

# Тест
pdf_file = "C://Users//yurav//PycharmProjects//DocStitcher//Ivannikov Court Cases.pdf"  # Замени на свой путь
output_pdf, page_info = normalize_pdf_size(pdf_file)