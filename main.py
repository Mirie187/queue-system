from fastapi import FastAPI
from database import SessionLocal, engine, Base
from models import Customer, Counter
from datetime import datetime, date
from sqlalchemy import func, extract
app = FastAPI()
Base.metadata.create_all(bind=engine)
AVERAGE_SERVICE_MINUTES = 2

@app.get("/")
def root():
    return {"message": "Queue system is running"}

@app.on_event("startup")
def create_counters():
    db = SessionLocal()

    existing = db.query(Counter).count()

    if existing == 0:
        db.add_all([
            Counter(name="Counter 1"),
            Counter(name="Counter 2"),
            Counter(name="Counter 3")
        ])
        db.commit()

    db.close()

@app.get("/status")
def show_status():
    db = SessionLocal()

    waiting = db.query(Customer).filter(Customer.status == "waiting").all()
    counters = db.query(Counter).all()

    counter_status = {}

    for counter in counters:
        if counter.current_customer_id:
            customer = db.query(Customer).filter(
    Customer.id == counter.current_customer_id
).first()

            counter_status[counter.name] = customer.ticket_number
        else:
            counter_status[counter.name] = None

    return {
        "waiting_customers": [c.ticket_number for c in waiting],
        "counters": counter_status
    }


    

def assign_customer(db):
    free_counter = db.query(Counter).filter(
        Counter.current_customer_id == None
    ).first()

    if not free_counter:
        return

    waiting_customer = db.query(Customer).filter(
        Customer.status == "waiting"
    ).order_by(Customer.id.asc())\
     .with_for_update(skip_locked=True)\
     .first()

    if not waiting_customer:
        return

    free_counter.current_customer_id = waiting_customer.id
    waiting_customer.status = "serving"
    waiting_customer.served_at = datetime.utcnow()
    waiting_customer.counter_name = free_counter.name


    db.commit()


@app.post("/customers")
def add_customer():
    db = SessionLocal()
    today = date.today()

    # count how many customers already came today
    today_count = db.query(Customer).filter(
        Customer.service_date == today
    ).count()

    ticket_number = f"C{today_count + 1:03d}"

    # Count how many customers are currently waiting
    waiting_count = db.query(Customer).filter(
        Customer.status == "waiting"
    ).count()

    # Estimated wait time
    estimated_wait = waiting_count * AVERAGE_SERVICE_MINUTES

    customer = Customer(
        ticket_number=ticket_number,
        status="waiting",
        service_date=today
    )

    db.add(customer)
    db.commit()
    db.refresh(customer)

    assign_customer(db)

    return {
        "ticket_number": ticket_number,
        "status": "waiting",
        "people_ahead": waiting_count,
        "estimated_wait_minutes": estimated_wait
    }


   
    
@app.post("/counters/{counter_name}/finish")
def finish_service(counter_name: str):
    db = SessionLocal()

    # Find the counter
    counter = db.query(Counter).filter(Counter.name == counter_name).first()

    if not counter:
        return {"error": "Invalid counter name"}

    if not counter.current_customer_id:
        return {"message": f"{counter_name} has no customer"}

    # Get the customer being served
    customer = db.query(Customer).get(counter.current_customer_id)

    # Mark customer as finished
    customer.status = "finished"
    customer.finished_at = datetime.utcnow()


    # Free the counter
    counter.current_customer_id = None

    db.commit()

    # Auto-assign next waiting customer
    assign_customer(db)

    return {
        "message": f"{customer.ticket_number} finished at {counter_name}"
    }
#reports and analytics endpoints
@app.get("/reports/served-today")
def served_today():
    db = SessionLocal()
    today = date.today()

    count = db.query(Customer).filter(
        Customer.service_date == today,
        Customer.status == "finished"
    ).count()

    return {"served_today": count}



#report for each server

@app.get("/reports/by-counter")
def served_by_counter():
    db = SessionLocal()
    today = date.today()

    results = db.query(
        Customer.counter_name,
        func.count(Customer.id)
    ).filter(
        Customer.service_date == today,
        Customer.status == "finished"
    ).group_by(Customer.counter_name).all()

    db.close()

    # Convert list of tuples into dictionary for clarity
    return {counter: count for counter, count in results}



@app.get("/reports/peak-hours")
def peak_hours():
    db = SessionLocal()
    today = date.today()

    results = db.query(
        extract("hour", Customer.created_at).label("hour"),
        func.count(Customer.id).label("customers")
    ).filter(
        Customer.service_date == today
    ).group_by("hour").order_by("hour").all()

    db.close()

    # Convert to dict for readability
    return {int(hour): count for hour, count in results}







