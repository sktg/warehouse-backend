from fastapi import FastAPI
from database import engine, Base, SessionLocal
from models import Order, Task, Product, Resource, StorageBin
from datetime import datetime
import random
import joblib
import pandas as pd
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel

ml_model = None
model_columns = None


# ---------- LIFESPAN (Render safe startup) ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global ml_model, model_columns
    ml_model = joblib.load("task_time_model.pkl")
    model_columns = joblib.load("model_columns.pkl")
    Base.metadata.create_all(bind=engine)
    print("Startup successful")
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

        num_tasks = random.randint(1, 3)
        products = db.query(Product).all()

        for i in range(num_tasks):
            product = random.choice(products)
            pallet_no = get_next_pallet_no(db)
            qty = random.choice([100,150,200,250,300,350,400,450,500])

            task = Task(
                order_no=order_no,
                task_no=i+1,
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

        db.commit()
        return {"message": f"Order {order_no} created"}

    finally:
        db.close()


# ---------- Allocate Tasks ----------
@app.post("/allocate_tasks")
def allocate_tasks():
    db = SessionLocal()
    try:
        open_tasks = db.query(Task).filter(Task.status == "OPEN").all()

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


# ---------- Read APIs ----------
@app.get("/tasks")
def get_tasks():
    db = SessionLocal()
    try:
        tasks = db.query(Task).all()
        return [{
            "task_id": t.id,
            "order_no": t.order_no,
            "product": t.product_name,
            "qty": t.source_qty,
            "status": t.status,
            "allocated_resource": t.allocated_resource
        } for t in tasks]
    finally:
        db.close()


@app.get("/dashboard")
def dashboard():
    db = SessionLocal()
    try:
        open_tasks = db.query(Task).filter(Task.status == "OPEN").count()
        allocated_tasks = db.query(Task).filter(Task.status == "ALLOCATED").count()
        completed_tasks = db.query(Task).filter(Task.status == "CONFIRMED").count()
        total_resources = db.query(Resource).count()
        busy_resources = db.query(Resource).filter(Resource.status == "Busy").count()

        utilization = (busy_resources / total_resources) * 100 if total_resources else 0

        return {
            "open_tasks": open_tasks,
            "assigned_tasks": allocated_tasks,
            "completed_tasks": completed_tasks,
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
