from sqlalchemy import text

def generate_task_no(db):
    next_val = db.execute(
        text("SELECT nextval('task_no_seq')")
    ).scalar()

    return f"TSK{next_val}"
