from database import engine, Base
import models  # импортируем модели, чтобы Base «увидел» их

def init_db():
    Base.metadata.drop_all(bind=engine)  # Удалить все таблицы
    Base.metadata.create_all(bind=engine)  # Создать заново

if __name__ == "__main__":
    init_db()
    print("Database tables created")
