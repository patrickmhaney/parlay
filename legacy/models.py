from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Numeric
from database import Base


class Bet(Base):
    __tablename__ = "bets"

    id = Column(Integer, primary_key=True, index=True)
    week = Column(Integer)
    #week = Column(Numeric(10,2))
    #week = Column(String, unique=False, index=True)
    bet_type = Column(String, unique=False, index=True)
    player_name = Column(String, unique=False, index=True)
    winning_team = Column(String, unique=False, index=True)
    losing_team = Column(String, unique=False, index=True)
    value = Column(String, unique=False, index=True)
    active_flag = Column(String, unique=False, index=True)

    

