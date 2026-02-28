from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, timedelta
from typing import Optional
from database import SessionLocal, engine, Base, get_db
import models
import auth

app = FastAPI()

# Create tables
Base.metadata.create_all(bind=engine)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Constants
AVERAGE_SERVICE_MINUTES = 2

# ==================== STATIC PAGES ====================

@app.get("/")
def root():
    return {"message": "Queue System is running"}

@app.get("/kiosk")
def kiosk_ui():
    return FileResponse("static/kiosk.html")

@app.get("/teller")
def teller_ui():
    return FileResponse("static/teller.html")

@app.get("/admin")
def admin_ui():
    return FileResponse("static/admin.html")

# ==================== INITIALIZATION ====================
@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    
    try:
        # Create default counters
        if db.query(models.Counter).count() == 0:
            counters = ["Counter 1", "Counter 2", "Counter 3"]
            for counter_name in counters:
                db.add(models.Counter(name=counter_name, is_active=True))
            db.commit()
            print("✅ Default counters created")
        
        # Create admin user
        admin = db.query(models.User).filter(models.User.username == "admin").first()
        if not admin:
            try:
                hashed_password = auth.get_password_hash("admin123")
                admin = models.User(
                    username="admin",
                    password_hash=hashed_password,
                    full_name="System Administrator",
                    role="admin",
                    is_active=True
                )
                db.add(admin)
                db.commit()
                print("✅ Admin user created (admin/admin123)")
            except Exception as e:
                print(f"⚠️ Error creating admin user: {e}")
                # Fallback: Create admin with a simpler password if bcrypt fails
                try:
                    # Try with a shorter password
                    hashed_password = auth.get_password_hash("admin")
                    admin = models.User(
                        username="admin",
                        password_hash=hashed_password,
                        full_name="System Administrator",
                        role="admin",
                        is_active=True
                    )
                    db.add(admin)
                    db.commit()
                    print("✅ Admin user created with fallback password (admin/admin)")
                except Exception as e2:
                    print(f"❌ Could not create admin user: {e2}")
        
    except Exception as e:
        print(f"⚠️ Startup error: {e}")
    finally:
        db.close()

# ==================== AUTHENTICATION ====================

@app.post("/auth/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    user.last_login_at = datetime.utcnow()
    db.commit()
    
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
        "full_name": user.full_name
    }

@app.get("/auth/me")
async def read_users_me(current_user: models.User = Depends(auth.get_current_active_user)):
    counter_name = None
    if current_user.current_counter_id:
        counter = current_user.current_counter_id
        # We need to query the counter name
        db = SessionLocal()
        counter_obj = db.query(models.Counter).filter(models.Counter.id == current_user.current_counter_id).first()
        if counter_obj:
            counter_name = counter_obj.name
        db.close()
    
    return {
        "username": current_user.username,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "current_counter_id": current_user.current_counter_id,
        "current_counter_name": counter_name
    }

# ==================== KIOSK ENDPOINTS ====================

@app.post("/customers")
def add_customer(db: Session = Depends(get_db)):
    today = date.today()

    last_customer = db.query(models.Customer).filter(
        models.Customer.service_date == today
    ).order_by(models.Customer.id.desc()).first()

    if last_customer:
        last_number = int(last_customer.ticket_number[1:])
        next_number = last_number + 1
    else:
        next_number = 1

    ticket_number = f"C{next_number:03d}"

    waiting_count = db.query(models.Customer).filter(
        models.Customer.status == "waiting"
    ).count()

    estimated_wait = waiting_count * AVERAGE_SERVICE_MINUTES

    customer = models.Customer(
        ticket_number=ticket_number,
        status="waiting",
        service_date=today
    )

    db.add(customer)
    db.commit()
    db.refresh(customer)

    return {
        "ticket_number": ticket_number,
        "people_ahead": waiting_count,
        "estimated_wait_minutes": estimated_wait
    }

@app.get("/status")
def show_status(db: Session = Depends(get_db)):
    waiting = db.query(models.Customer).filter(models.Customer.status == "waiting").all()
    waiting_count = len(waiting)
    
    counters = db.query(models.Counter).all()
    counter_status = {}

    for counter in counters:
        teller_name = None
        if counter.current_teller_id:
            teller = db.query(models.User).filter(models.User.id == counter.current_teller_id).first()
            teller_name = teller.full_name if teller else None
        
        customer_info = None
        if counter.current_customer_id:
            customer = db.query(models.Customer).filter(models.Customer.id == counter.current_customer_id).first()
            if customer:
                customer_info = {
                    "ticket": customer.ticket_number,
                    "waiting_since": customer.created_at.isoformat() if customer.created_at else None
                }
        
        counter_status[counter.name] = {
            "teller": teller_name,
            "customer": customer_info,
            "is_active": counter.is_active
        }

    return {
        "waiting_customers": [c.ticket_number for c in waiting],
        "waiting_count": waiting_count,
        "counters": counter_status
    }

# ==================== TELLER ENDPOINTS ====================

@app.get("/counters/available")
def get_available_counters(
    current_user: models.User = Depends(auth.require_teller),
    db: Session = Depends(get_db)
):
    available = db.query(models.Counter).filter(
        models.Counter.current_teller_id == None,
        models.Counter.is_active == True
    ).all()
    
    busy = db.query(models.Counter).filter(
        models.Counter.current_teller_id != None
    ).all()
    
    busy_list = []
    for c in busy:
        teller = db.query(models.User).filter(models.User.id == c.current_teller_id).first()
        busy_list.append({
            "id": c.id,
            "name": c.name,
            "teller": teller.full_name if teller else "Unknown"
        })
    
    return {
        "available": [{"id": c.id, "name": c.name} for c in available],
        "busy": busy_list
    }

@app.post("/teller/select-counter/{counter_id}")
def select_counter(
    counter_id: int,
    current_user: models.User = Depends(auth.require_teller),
    db: Session = Depends(get_db)
):
    counter = db.query(models.Counter).filter(models.Counter.id == counter_id).first()
    if not counter:
        raise HTTPException(status_code=404, detail="Counter not found")
    
    if counter.current_teller_id:
        raise HTTPException(status_code=400, detail="Counter is already occupied")
    
    if not counter.is_active:
        raise HTTPException(status_code=400, detail="Counter is inactive")
    
    # If teller was at another counter, free that counter
    if current_user.current_counter_id:
        old_counter = db.query(models.Counter).filter(models.Counter.id == current_user.current_counter_id).first()
        if old_counter:
            old_counter.current_teller_id = None
    
    # Assign to new counter
    counter.current_teller_id = current_user.id
    current_user.current_counter_id = counter.id
    current_user.last_login_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "message": f"You are now working at {counter.name}",
        "counter": counter.name,
        "counter_id": counter.id
    }

@app.post("/teller/leave-counter")
def leave_counter(
    current_user: models.User = Depends(auth.require_teller),
    db: Session = Depends(get_db)
):
    if not current_user.current_counter_id:
        return {"message": "You are not at any counter"}
    
    counter = db.query(models.Counter).filter(models.Counter.id == current_user.current_counter_id).first()
    
    if counter:
        # If there's a customer being served, put them back in queue
        if counter.current_customer_id:
            customer = db.query(models.Customer).filter(models.Customer.id == counter.current_customer_id).first()
            if customer and customer.status == "serving":
                customer.status = "waiting"
                customer.counter_id = None
                customer.served_by_id = None
            counter.current_customer_id = None
        
        counter.current_teller_id = None
    
    current_user.current_counter_id = None
    db.commit()
    
    return {"message": f"You have left the counter"}

@app.get("/teller/status")
def teller_status(
    current_user: models.User = Depends(auth.require_teller),
    db: Session = Depends(get_db)
):
    if not current_user.current_counter_id:
        return {
            "at_counter": False,
            "message": "No counter selected"
        }
    
    counter = db.query(models.Counter).filter(models.Counter.id == current_user.current_counter_id).first()
    
    current_customer = None
    if counter and counter.current_customer_id:
        customer = db.query(models.Customer).filter(models.Customer.id == counter.current_customer_id).first()
        if customer:
            wait_time = datetime.utcnow() - customer.created_at
            current_customer = {
                "ticket_number": customer.ticket_number,
                "waiting_since": customer.created_at.isoformat() if customer.created_at else None,
                "waiting_minutes": round(wait_time.total_seconds() / 60, 1)
            }
    
    waiting_count = db.query(models.Customer).filter(
        models.Customer.status == "waiting"
    ).count()
    
    served_today = db.query(models.Customer).filter(
        models.Customer.served_by_id == current_user.id,
        models.Customer.service_date == date.today(),
        models.Customer.status == "finished"
    ).count()
    
    return {
        "at_counter": True,
        "counter_name": counter.name if counter else None,
        "current_customer": current_customer,
        "waiting_customers": waiting_count,
        "served_today": served_today
    }

@app.post("/teller/next-customer")
def next_customer(
    current_user: models.User = Depends(auth.require_teller),
    db: Session = Depends(get_db)
):
    if not current_user.current_counter_id:
        raise HTTPException(status_code=400, detail="Select a counter first")
    
    counter = db.query(models.Counter).filter(models.Counter.id == current_user.current_counter_id).first()
    
    if counter.current_customer_id:
        return {"message": "You are already serving a customer"}
    
    next_customer = db.query(models.Customer).filter(
        models.Customer.status == "waiting"
    ).order_by(models.Customer.id.asc()).first()
    
    if not next_customer:
        return {"message": "No customers waiting"}
    
    next_customer.status = "serving"
    next_customer.served_at = datetime.utcnow()
    next_customer.counter_id = counter.id
    next_customer.served_by_id = current_user.id
    
    counter.current_customer_id = next_customer.id
    
    db.commit()
    
    wait_time = datetime.utcnow() - next_customer.created_at
    
    return {
        "ticket_number": next_customer.ticket_number,
        "waiting_minutes": round(wait_time.total_seconds() / 60, 1),
        "counter": counter.name
    }

@app.post("/teller/complete-service")
def complete_service(
    current_user: models.User = Depends(auth.require_teller),
    db: Session = Depends(get_db)
):
    if not current_user.current_counter_id:
        raise HTTPException(status_code=400, detail="Select a counter first")
    
    counter = db.query(models.Counter).filter(models.Counter.id == current_user.current_counter_id).first()
    
    if not counter.current_customer_id:
        return next_customer(current_user, db)
    
    customer = db.query(models.Customer).filter(models.Customer.id == counter.current_customer_id).first()
    customer.status = "finished"
    customer.finished_at = datetime.utcnow()
    
    counter.current_customer_id = None
    db.commit()
    
    return next_customer(current_user, db)

# ==================== ADMIN ENDPOINTS ====================

@app.get("/admin/users")
def get_all_users(
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db)
):
    users = db.query(models.User).all()
    
    result = []
    for user in users:
        served_today = 0
        if user.role == "teller":
            served_today = db.query(models.Customer).filter(
                models.Customer.served_by_id == user.id,
                models.Customer.service_date == date.today(),
                models.Customer.status == "finished"
            ).count()
        
        counter_name = None
        if user.current_counter_id:
            counter = db.query(models.Counter).filter(models.Counter.id == user.current_counter_id).first()
            counter_name = counter.name if counter else None
        
        result.append({
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "current_counter": counter_name,
            "served_today": served_today
        })
    
    return result

@app.post("/admin/users")
def create_user(
    username: str,
    password: str,
    full_name: str,
    role: str,
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db)
):
    if role not in ["admin", "teller"]:
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'teller'")
    
    existing = db.query(models.User).filter(models.User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    hashed_password = auth.get_password_hash(password)
    user = models.User(
        username=username,
        password_hash=hashed_password,
        full_name=full_name,
        role=role,
        is_active=True
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return {"message": f"User {username} created", "user_id": user.id}

@app.put("/admin/users/{user_id}/toggle")
def toggle_user(
    user_id: int,
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = not user.is_active
    
    if not user.is_active and user.current_counter_id:
        counter = db.query(models.Counter).filter(models.Counter.id == user.current_counter_id).first()
        if counter:
            counter.current_teller_id = None
        user.current_counter_id = None
    
    db.commit()
    
    return {
        "message": f"User {user.username} {'activated' if user.is_active else 'deactivated'}",
        "is_active": user.is_active
    }

@app.get("/admin/counters")
def get_all_counters(
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db)
):
    counters = db.query(models.Counter).all()
    
    result = []
    for counter in counters:
        today_served = db.query(models.Customer).filter(
            models.Customer.counter_id == counter.id,
            models.Customer.service_date == date.today(),
            models.Customer.status == "finished"
        ).count()
        
        current_customer = None
        if counter.current_customer_id:
            customer = db.query(models.Customer).filter(models.Customer.id == counter.current_customer_id).first()
            if customer:
                current_customer = {
                    "ticket": customer.ticket_number
                }
        
        teller_name = None
        if counter.current_teller_id:
            teller = db.query(models.User).filter(models.User.id == counter.current_teller_id).first()
            teller_name = teller.full_name if teller else None
        
        result.append({
            "id": counter.id,
            "name": counter.name,
            "is_active": counter.is_active,
            "current_teller": teller_name,
            "current_customer": current_customer,
            "today_served": today_served,
            "occupied": counter.current_teller_id is not None
        })
    
    return result

@app.post("/admin/counters")
def create_counter(
    name: str,
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db)
):
    existing = db.query(models.Counter).filter(models.Counter.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Counter name already exists")
    
    counter = models.Counter(name=name, is_active=True)
    db.add(counter)
    db.commit()
    db.refresh(counter)
    
    return {"message": f"Counter {name} created", "counter_id": counter.id}

@app.put("/admin/counters/{counter_id}/toggle")
def toggle_counter(
    counter_id: int,
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db)
):
    counter = db.query(models.Counter).filter(models.Counter.id == counter_id).first()
    if not counter:
        raise HTTPException(status_code=404, detail="Counter not found")
    
    counter.is_active = not counter.is_active
    
    if not counter.is_active and counter.current_teller_id:
        teller = db.query(models.User).filter(models.User.id == counter.current_teller_id).first()
        if teller:
            teller.current_counter_id = None
        counter.current_teller_id = None
    
    db.commit()
    
    return {
        "message": f"Counter {counter.name} {'activated' if counter.is_active else 'deactivated'}",
        "is_active": counter.is_active
    }

# ==================== REPORTS ====================

@app.get("/reports/served-today")
def served_today(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    count = db.query(models.Customer).filter(
        models.Customer.service_date == date.today(),
        models.Customer.status == "finished"
    ).count()
    
    return {"served_today": count}

@app.get("/admin/reports/teller-summary")
def teller_summary(
    period: str = "today",
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db)
):
    today = date.today()
    if period == "today":
        start_date = today
        end_date = today
    elif period == "week":
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif period == "month":
        start_date = today.replace(day=1)
        next_month = today.replace(day=28) + timedelta(days=4)
        end_date = next_month - timedelta(days=next_month.day)
    else:
        raise HTTPException(status_code=400, detail="Invalid period")
    
    tellers = db.query(models.User).filter(models.User.role == "teller").all()
    
    result = []
    for teller in tellers:
        customers = db.query(models.Customer).filter(
            models.Customer.served_by_id == teller.id,
            models.Customer.service_date.between(start_date, end_date),
            models.Customer.status == "finished"
        ).all()
        
        total_served = len(customers)
        
        avg_service = 0
        if total_served > 0:
            service_times = []
            for c in customers:
                if c.finished_at and c.served_at:
                    minutes = (c.finished_at - c.served_at).total_seconds() / 60
                    service_times.append(minutes)
            if service_times:
                avg_service = sum(service_times) / len(service_times)
        
        result.append({
            "name": teller.full_name,
            "username": teller.username,
            "served": total_served,
            "avg_service_time": round(avg_service, 2),
            "current_status": "Working" if teller.current_counter_id else "Offline"
        })
    
    return {
        "period": period,
        "tellers": result
    }