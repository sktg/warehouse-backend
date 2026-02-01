from fastapi import FastAPI
from database import engine, Base, SessionLocal
from models import Order, Task, Product, Resource, StorageBin
from datetime import datetime
import random
import joblib
import pandas as pd
from fastapi.middleware.cors import CORSMiddleware

ml_model = joblib.load("task_time_model.pkl")
model_columns = joblib.load("model_columns.pkl")

app = FastAPI() # 👈 THIS MUST COME BEFORE add_middleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # <-- important
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)






Base.metadata.create_all(bind=engine)


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


@app.get("/")
def home():
    return {"message": "Warehouse Backend Running"}


from fastapi import Body

@app.post("/create_order")
def create_order(priority: str = Body(...)):
    db = SessionLocal()

    order_no = get_next_order_no(db)
    now = datetime.now()

    order = Order(
        order_no=order_no,
        priority=priority,
        created_date=now.strftime("%d-%m-%Y"),
        created_time=now.strftime("%H:%M:%S"),
        status="OPEN"
    )
    db.add(order)

    # 1 to 3 tasks
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
    db.close()

    return {"message": f"Order {order_no} created with {num_tasks} tasks"}

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


@app.post("/allocate_tasks")
def allocate_tasks():
    db = SessionLocal()

    open_tasks = db.query(Task).filter(Task.status == "OPEN").all()

    st_to_rt = {
        "ST01": "RT01",
        "ST02": "RT02",
        "ST03": "RT03",
    }

    for task in open_tasks:
        required_rt = st_to_rt[task.storage_type]

        # Get all available resources of correct type
        available_resources = db.query(Resource).filter(
            Resource.resource_type == required_rt,
            Resource.status == "Available"
        ).all()
        if not available_resources:
            continue

        best_resource = None
        best_time = float("inf")

        for res in available_resources:
            predicted_time = predict_time(res.resource_code)

            if predicted_time < best_time:
                best_time = predicted_time
                best_resource = res

        if best_resource:
            task.allocated_resource = best_resource.resource_code
            task.status = "ALLOCATED"
            best_resource.status = "Busy"

            order = db.query(Order).filter(
                Order.order_no == task.order_no
            ).first()
            order.status = "ALLOCATED"
            db.flush()

    db.commit()
    db.close()

    return {"message": "Tasks allocated using ML"}


@app.post("/confirm_task/{task_id}")
def confirm_task(task_id: int):
    db = SessionLocal()

    task = db.query(Task).filter(Task.id == task_id).first()

    if not task or task.status != "ALLOCATED":
        return {"error": "Task not found or not allocated"}

    now = datetime.now()

    task.status = "CONFIRMED"
    task.confirmed_by = task.allocated_resource
    task.confirmation_date = now.strftime("%d-%m-%Y")
    task.confirmation_time = now.strftime("%H:%M:%S")
    task.destination_qty = task.source_qty

    # Deduct stock from source bin
    bin = db.query(StorageBin).filter(
        StorageBin.bin_code == task.source_bin
    ).first()

    if bin and bin.current_qty >= task.source_qty:
        bin.current_qty -= task.source_qty
    else:
        return {"error": f"Product not available in bin {task.source_bin}. Please refill inventory."}


    # Free the resource
    resource = db.query(Resource).filter(
        Resource.resource_code == task.allocated_resource
    ).first()

    resource.status = "Available"

    # Check if all tasks of order are confirmed
    pending = db.query(Task).filter(
        Task.order_no == task.order_no,
        Task.status != "CONFIRMED"
    ).count()

    if pending == 0:
        order = db.query(Order).filter(
            Order.order_no == task.order_no
        ).first()
        order.status = "CONFIRMED"

    db.commit()
    db.close()

    return {"message": f"Task {task_id} confirmed"}

@app.get("/tasks")
def get_tasks():
    db = SessionLocal()
    tasks = db.query(Task).all()

    result = []
    for t in tasks:
        result.append({
            "task_id": t.id,
            "order_no": t.order_no,
            "product": t.product_name,
            "qty": t.source_qty,
            "status": t.status,
            "allocated_resource": t.allocated_resource
        })

    db.close()
    return result

@app.get("/dashboard")
def dashboard():
    db = SessionLocal()

    open_tasks = db.query(Task).filter(Task.status == "OPEN").count()
    allocated_tasks = db.query(Task).filter(Task.status == "ALLOCATED").count()
    completed_tasks = db.query(Task).filter(Task.status == "CONFIRMED").count()

    total_resources = db.query(Resource).count()
    busy_resources = db.query(Resource).filter(Resource.status == "Busy").count()

    utilization = (busy_resources / total_resources) * 100 if total_resources else 0

    db.close()

    return {
        "open_tasks": open_tasks,
        "assigned_tasks": allocated_tasks,
        "completed_tasks": completed_tasks,
        "resource_utilization_percent": round(utilization, 2)
    }


@app.get("/bins")
def get_bins():
    db = SessionLocal()
    bins = db.query(StorageBin).all()

    result = []
    for b in bins:
        result.append({
            "bin_code": b.bin_code,
            "capacity": b.capacity,
            "current_qty": b.current_qty
        })

    db.close()
    return result


@app.post("/refill_bin/{bin_code}")
def refill_bin(bin_code: str):
    db = SessionLocal()

    bin = db.query(StorageBin).filter(
        StorageBin.bin_code == bin_code
    ).first()

    if not bin:
        return {"error": "Bin not found"}

    bin.current_qty = min(bin.capacity, bin.current_qty + 500)

    db.commit()
    db.close()

    return {"message": f"{bin_code} refilled by 500"}


