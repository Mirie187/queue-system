from database import Base

from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship

from datetime import datetime, date


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)

    ticket_number = Column(String, nullable=False)
    status = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)
    served_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    counter_name = Column(String, nullable=True)

    service_date = Column(Date, default=date.today)

class Counter(Base):
    __tablename__ = "counters"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, unique=True)

    current_customer_id = Column(
        Integer,
        ForeignKey("customers.id"),
        nullable=True
    )