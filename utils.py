from sqlalchemy.orm import Session
from models import Task

def generate_task_no(db: Session):
    last_task = db.query(Task).order_by(Task.id.desc()).first()

    if not last_task or not last_task.task_no:
        return "TSK90001"

    last_number = int(last_task.task_no.replace("TSK", ""))
    next_number = last_number + 1

    return f"TSK{next_number}"
