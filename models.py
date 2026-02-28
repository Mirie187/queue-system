from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, date

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
    current_counter_id = Column(Integer, ForeignKey("counters.id"), nullable=True)

class Counter(Base):
    __tablename__ = "counters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    current_teller_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    current_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    ticket_number = Column(String, nullable=False)
    status = Column(String)  # 'waiting', 'serving', 'finished'
    created_at = Column(DateTime, default=datetime.utcnow)
    served_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    counter_id = Column(Integer, ForeignKey("counters.id"), nullable=True)
    served_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    service_date = Column(Date, default=date.today)