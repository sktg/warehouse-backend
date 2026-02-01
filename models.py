from sqlalchemy import Column, Integer, String
from database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    order_no = Column(String, unique=True)
    priority = Column(String)
    created_date = Column(String)
    created_time = Column(String)
    status = Column(String, default="OPEN")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    order_no = Column(String)
    task_no = Column(Integer)

    product_name = Column(String)
    product_code = Column(String)
    storage_type = Column(String)
    source_qty = Column(Integer)

    created_date = Column(String)
    created_time = Column(String)

    status = Column(String, default="OPEN")

    warehouse_process_type = Column(String, default="YR10")
    activity = Column(String, default="PICK")
    batch = Column(String, default="BAT123")
    created_by = Column(String, default="SUPERVISOR 1")
    stock_type = Column(String, default="SL")
    owner_wh = Column(String, default="1001")
    uom = Column(String, default="EA")

    pallet_hu = Column(String)

    # Allocation stage
    allocated_resource = Column(String, nullable=True)

    # Confirmation stage
    confirmed_by = Column(String, nullable=True)
    confirmation_date = Column(String, nullable=True)
    confirmation_time = Column(String, nullable=True)
    destination_qty = Column(Integer, nullable=True)
    source_bin = Column(String, nullable=True)
    dest_storage_type = Column(String, default="GIZN")
    dest_bin = Column(String, nullable=True)


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True)
    resource_code = Column(String, unique=True)
    resource_type = Column(String)
    status = Column(String, default="Available")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    product_name = Column(String)
    product_code = Column(String)
    storage_type = Column(String)
    source_bin = Column(String)


class StorageBin(Base):
    __tablename__ = "storage_bins"

    id = Column(Integer, primary_key=True)
    bin_code = Column(String, unique=True)
    capacity = Column(Integer, default=1000)
    current_qty = Column(Integer, default=1000)
