from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import math

Base = declarative_base()


class Match(Base):
    """Модель для хранения информации о матчах."""
    __tablename__ = 'matches'

    id = Column(Integer, primary_key=True)
    player1 = Column(String, nullable=False)
    player2 = Column(String, nullable=False)
    winner = Column(String, nullable=True)
    system = Column(String, nullable=False)
