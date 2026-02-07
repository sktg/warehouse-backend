from fastapi import FastAPI
from database import engine, Base, SessionLocal
from models import * # ensures all tables are registered
from datetime import datetime
import random
import joblib
import pandas as pd
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from seed_data import seed_database
from utils import generate_task_no
ml_model = None
model_columns = None


# ---------- LIFESPAN (Render safe startup) ----------
from seed_data import seed_database
from models import *  # ensures SQLAlchemy registers all tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ml_model, model_columns

    ml_model = joblib.load("task_time_model.pkl")
    model_columns = joblib.load("model_columns.pkl")

    Base.metadata.create_all(bind=engine)



    seed_database()
    print("✅ Tables created, sequence created, DB seeded")

    yield





app = FastAPI(lifespan=lifespan)

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import Request

@app.options("/{full_path:path}")
async def options_handler(request: Request, full_path: str):
    return {}


# ---------- Helpers ----------
def get_next_order_no(db):
    last = db.query(Order).order_by(Order.id.desc()).first()
    if not last:
        return "ORD100001"
    num = int(last.order_no.replace("ORD", ""))
    return f"ORD{num+1}"


def get_next_pallet_no(db):
    last = db.query(Task).order_by(Task.id.desc()).first()
    if not last or not last.pallet_hu:
        return "900129"
    return str(int(last.pallet_hu) + 1)


def predict_time(resource_code):
    now = datetime.now()
    data = pd.DataFrame([{
        "Warehouse Task": "WT01",
        "Task Type": "Picking",
        "Resource Allocated": resource_code,
        "hour": now.hour,
        "day_of_week": now.weekday(),
        "is_afternoon": 1 if now.hour >= 13 else 0
    }])

    data = pd.get_dummies(data)
    data = data.reindex(columns=model_columns, fill_value=0)
    return ml_model.predict(data)[0]


def get_priority_score(priority: str):
    return {
        "P1": 10000,
        "P2": 400,
        "P3": 300,
        "P4": 200,
        "P5": 100,
    }.get(priority, 0)

@app.get("/orders")
def get_orders():
    db = SessionLocal()
    try:
        orders = db.query(Order).all()
        result = []

        for o in orders:
            total_items = db.query(Task).filter(
                Task.order_no == o.order_no
            ).count()

            completed_items = db.query(Task).filter(
                Task.order_no == o.order_no,
                Task.status == "CONFIRMED"
            ).count()

            derived_status = (
                "CONFIRMED"
                if completed_items == total_items and total_items > 0
                else o.status
            )

            result.append({
                "order_no": o.order_no,
                "priority": o.priority,
                "total_items": total_items,
                "completed_items": completed_items,
                "raised_time": f"{o.created_date} {o.created_time}",
                "status": derived_status
            })

        return result
    finally:
        db.close()


@app.get("/completed_orders")
def completed_orders():
    db = SessionLocal()
    try:
        orders = db.query(Order).filter(
            Order.status == "CONFIRMED"
        ).all()

        result = []
        for o in orders:
            total_items = db.query(Task).filter(
                Task.order_no == o.order_no
            ).count()

            result.append({
                "order_no": o.order_no,
                "priority": o.priority,
                "total_items": total_items,
                "completed_items": total_items,
                "raised_time": f"{o.created_date} {o.created_time}"
            })

        return result

    finally:
        db.close()


# ---------- Routes ----------
@app.get("/")
def home():
    return {"message": "Warehouse Backend Running"}


class OrderRequest(BaseModel):
    priority: str


# ---------- Create Order ----------
@app.post("/create_order")
def create_order(req: OrderRequest):
    db = SessionLocal()
    try:
        order_no = get_next_order_no(db)
        now = datetime.now()

        order = Order(
            order_no=order_no,
            priority=req.priority,
            created_date=now.strftime("%d-%m-%Y"),
            created_time=now.strftime("%H:%M:%S"),
            status="OPEN"
        )
        db.add(order)

        num_tasks = random.randint(1, 9)
        products = db.query(Product).all()

        # ✅ SAFETY — prevents crash when DB is empty on Render
        if not products:
            return {"error": "No products found in database. Seed data missing."}

        created_tasks = []

        for i in range(num_tasks):
            product = random.choice(products)
            pallet_no = get_next_pallet_no(db)
            qty = random.choice([100,150,200,250,300,350,400,450,500])

            task = Task(
                order_no=order_no,
                product_name=product.product_name,
                product_code=product.product_code,
                storage_type=product.storage_type,
                source_qty=qty,
                created_date=now.strftime("%d-%m-%Y"),
                created_time=now.strftime("%H:%M:%S"),
                pallet_hu=pallet_no,
                source_bin=product.source_bin,
                dest_bin={
                    "ST01": "GIZN-001",
                    "ST02": "GIZN-002",
                    "ST03": "GIZN-003",
                }[product.storage_type]
            )

            db.add(task)
            created_tasks.append(task)

        # ⭐ Flush ONCE after all tasks are added
        db.flush()

        # ⭐ Now assign task numbers
        for task in created_tasks:
            task.task_no = generate_task_no(task.id)



        db.commit()
        return {"message": f"Order {order_no} created"}

    finally:
        db.close()


# ---------- Allocate Tasks ----------
@app.post("/allocate_tasks")
def allocate_tasks():
    db = SessionLocal()
    try:
        from datetime import datetime

        open_tasks = (
            db.query(Task, Order)
            .join(Order, Task.order_no == Order.order_no)
            .filter(Task.status == "OPEN")
            .all()
        )

        def effective_score(task, order):
            created = datetime.strptime(
                order.created_date + " " + order.created_time,
                "%d-%m-%Y %H:%M:%S"
            )
            waiting_minutes = (datetime.now() - created).total_seconds() / 60
            return get_priority_score(order.priority) + waiting_minutes

        # Sort tasks by dynamic priority
        open_tasks.sort(key=lambda x: effective_score(x[0], x[1]), reverse=True)

        # Keep only tasks after sorting
        open_tasks = [t[0] for t in open_tasks]


        st_to_rt = {"ST01": "RT01", "ST02": "RT02", "ST03": "RT03"}

        for task in open_tasks:
            required_rt = st_to_rt[task.storage_type]

            resources = db.query(Resource).filter(
                Resource.resource_type == required_rt,
                Resource.status == "Available"
            ).all()

            if not resources:
                continue

            best = min(resources, key=lambda r: predict_time(r.resource_code))

            task.allocated_resource = best.resource_code
            task.status = "ALLOCATED"
            best.status = "Busy"

            order = db.query(Order).filter(Order.order_no == task.order_no).first()
            order.status = "ALLOCATED"

            db.flush()

        db.commit()
        return {"message": "Tasks allocated"}

    finally:
        db.close()


# ---------- Confirm Task ----------
@app.post("/confirm_task/{task_id}")
def confirm_task(task_id: int):
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task or task.status != "ALLOCATED":
            return {"error": "Task not found or not allocated"}

        now = datetime.now()
        task.status = "CONFIRMED"
        task.confirmed_by = task.allocated_resource
        task.confirmation_date = now.strftime("%d-%m-%Y")
        task.confirmation_time = now.strftime("%H:%M:%S")
        task.destination_qty = task.source_qty

        bin = db.query(StorageBin).filter(StorageBin.bin_code == task.source_bin).first()
        if not bin or bin.current_qty < task.source_qty:
            return {"error": f"Product not available in bin {task.source_bin}. Please refill inventory."}

        bin.current_qty -= task.source_qty

        resource = db.query(Resource).filter(
            Resource.resource_code == task.allocated_resource
        ).first()
        resource.status = "Available"

        pending = db.query(Task).filter(
            Task.order_no == task.order_no,
            Task.status != "CONFIRMED"
        ).count()

        if pending == 0:
            order = db.query(Order).filter(Order.order_no == task.order_no).first()
            order.status = "CONFIRMED"

        db.commit()
        return {"message": f"Task {task_id} confirmed"}

    finally:
        db.close()


# ---------- Read APIs ----------#added priority and rank values
@app.get("/tasks")
def get_tasks():
    db = SessionLocal()
    try:
        tasks = db.query(Task).all()
        orders = db.query(Order).all()

        # ---------- Build dynamic order ranking ----------
        priority_weight = {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}

        order_scores = []
        for o in orders:
            open_tasks = db.query(Task).filter(
                Task.order_no == o.order_no,
                Task.status == "OPEN"
            ).count()

            score = (
                priority_weight.get(o.priority, 5) * 1000
                + open_tasks * 10
                + o.id
            )
            order_scores.append((o.order_no, score, o.priority))

        # Sort by score → lowest score = highest priority
        order_scores.sort(key=lambda x: x[1])

        # Map order_no → rank
        order_rank_map = {}
        for idx, (order_no, _, pr) in enumerate(order_scores, start=1):
            order_rank_map[order_no] = (idx, pr)

        # ---------- Build task response ----------
        result = []
        for t in tasks:
            rank, base_pr = order_rank_map.get(t.order_no, ("", ""))

            result.append({
                "task_id": t.id,
                "task_no": t.task_no,   # ⭐ ADD THIS
                "order_no": t.order_no,
                "product": t.product_name,
                "qty": t.source_qty,
                "status": t.status,
                "allocated_resource": t.allocated_resource,
                "base_priority": base_pr,
                "current_rank": rank
            })

        return result

    finally:
        db.close()



@app.get("/dashboard")
def dashboard():
    db = SessionLocal()
    try:
        open_tasks = db.query(Task).filter(Task.status == "OPEN").count()
        allocated_tasks = db.query(Task).filter(Task.status == "ALLOCATED").count()
        completed_tasks = db.query(Task).filter(Task.status == "CONFIRMED").count()

        completed_orders = db.query(Order).filter(
            Order.status == "CONFIRMED"
        ).count()

        total_resources = db.query(Resource).count()
        busy_resources = db.query(Resource).filter(Resource.status == "Busy").count()

        utilization = (busy_resources / total_resources) * 100 if total_resources else 0

        return {
            "open_tasks": open_tasks,
            "assigned_tasks": allocated_tasks,
            "completed_tasks": completed_tasks,
            "completed_orders": completed_orders,   # ⭐ NEW
            "resource_utilization_percent": round(utilization, 2)
        }
    finally:
        db.close()



@app.get("/bins")
def get_bins():
    db = SessionLocal()
    try:
        bins = db.query(StorageBin).all()
        return [{
            "bin_code": b.bin_code,
            "capacity": b.capacity,
            "current_qty": b.current_qty
        } for b in bins]
    finally:
        db.close()


@app.post("/refill_bin/{bin_code}")
def refill_bin(bin_code: str):
    db = SessionLocal()
    try:
        bin = db.query(StorageBin).filter(StorageBin.bin_code == bin_code).first()
        if not bin:
            return {"error": "Bin not found"}

        bin.current_qty = min(bin.capacity, bin.current_qty + 500)
        db.commit()
        return {"message": f"{bin_code} refilled"}
    finally:
        db.close()

@app.get("/resource_status")
def resource_status():
    db = SessionLocal()
    try:
        resources = db.query(Resource).all()
        result = []

        for r in resources:
            task = db.query(Task).filter(
                Task.allocated_resource == r.resource_code,
                Task.status == "ALLOCATED"
            ).first()

            result.append({
                "resource_code": r.resource_code,
                "resource_type": r.resource_type,
                "resource_name": r.resource_name,
                "status": r.status,
                "product": task.product_name if task else None,
                "task_no": task.task_no if task else None,
                "source_bin": task.source_bin if task else None,
                "dest_bin": task.dest_bin if task else None,
            })

        return result
    finally:
        db.close()

@app.get("/resource/{code}")
def resource_details(code: str):
    db = SessionLocal()
    try:
        tasks = db.query(Task).filter(
            Task.allocated_resource == code
        ).order_by(Task.id.desc()).all()

        completed = len([t for t in tasks if t.status == "CONFIRMED"])
        current_task = next((t for t in tasks if t.status == "ALLOCATED"), None)

        return {
            "resource_code": code,
            "total_completed": completed,
            "current_task": {
                "task_id": current_task.id,
                "task_no": current_task.task_no,
                "product": current_task.product_name,
                "source_bin": current_task.source_bin,
                "dest_bin": current_task.dest_bin,
            } if current_task else None,
            "history": [
                {
                    "task_id": t.id,  
                    "task_no": t.task_no,
                    "product": t.product_name,
                    "qty": t.source_qty,
                    "status": t.status
                } for t in tasks
            ]
        }
    finally:
        db.close()
