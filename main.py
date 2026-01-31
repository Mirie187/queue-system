from fastapi import FastAPI
from database import SessionLocal
from database import SessionLocal
from models import Customer, Counter
from datetime import datetime, date
app = FastAPI()

@app.get("/")
def root():
    return {"message": "Queue system is running"}

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

    customer = Customer(
        ticket_number=ticket_number,
        status="waiting",
        service_date=today
    )

    db.add(customer)
    db.commit()
    db.refresh(customer)
    assign_customer(db)

    return {"message": f"{ticket_number} added"}
   
    
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

    # Free the counter
    counter.current_customer_id = None

    db.commit()

    # Auto-assign next waiting customer
    assign_customer(db)

    return {
        "message": f"{customer.ticket_number} finished at {counter_name}"
    }



@app.post("/test-db")
def test_db():
    db = SessionLocal()

    customer = Customer(
        ticket_number="C001",
        status="waiting"
    )

    db.add(customer)
    db.commit()

    return {"message": "Customer inserted into database"}
