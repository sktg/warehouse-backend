from sqlalchemy import text

def generate_task_no(task_id: int):
    return f"TSK{90000 + task_id}"