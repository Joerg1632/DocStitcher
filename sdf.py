from pypdf import PdfReader

pdf_path = "扫描全能王 2025-02-10 10.23 (1).pdf"
reader = PdfReader(pdf_path)

# Основные метаданные
info = reader.metadata
print("Метаданные PDF:")
for k, v in info.items():
    print(f"{k}: {v}")

# Даты создания и последнего изменения
print("\nДата создания:", info.get("/CreationDate"))
print("Дата последнего изменения:", info.get("/ModDate"))

# Сколько страниц
print("Количество страниц:", len(reader.pages))
