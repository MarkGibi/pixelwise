import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

Base = declarative_base()


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True)
    prediction = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    model_version = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


DB_PASSWORD = os.getenv("DB_PASSWORD")
DATABASE_URL = f"postgresql://pixelwise:{DB_PASSWORD}@localhost/pixelwise"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
