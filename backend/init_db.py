from database import engine, Base
import models  # импортируем модели, чтобы Base «увидел» их

def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
    print("Database tables created")
