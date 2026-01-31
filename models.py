from sqlalchemy import Column, Integer, String, DateTime, Date
from datetime import datetime, date
from database import Base
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship




class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    ticket_number = Column(String)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    service_date = Column(Date, default=date.today)



class Counter(Base):
    __tablename__ = "counters"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    current_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)