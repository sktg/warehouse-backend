from database import SessionLocal, engine
from models import Base, Resource, Product, StorageBin

Base.metadata.create_all(bind=engine)

db = SessionLocal()

# ----------- RESOURCES -----------
resources = [
    ("RSG01","RT01"),("RSG02","RT01"),("RSG03","RT01"),
    ("RSG04","RT01"),("RSG05","RT01"),("RSG06","RT01"),
    ("RSG07","RT01"),("RSG08","RT01"),("RSG09","RT01"),
    ("RSG10","RT01"),
    ("RSG11","RT02"),("RSG12","RT02"),("RSG13","RT02"),
    ("RSG14","RT02"),("RSG15","RT02"),("RSG16","RT02"),
    ("RSG17","RT03"),("RSG18","RT03"),("RSG19","RT03"),
    ("RSG20","RT03"),("RSG21","RT03"),("RSG22","RT03"),
]

for code, rtype in resources:
    db.add(Resource(resource_code=code, resource_type=rtype))


# ----------- PRODUCTS -----------
products = [
    ("Soap1","88013","ST01","ST01-0001"),
    ("Soap2","88014","ST01","ST01-0002"),
    ("Soap3","88015","ST01","ST01-0003"),
    ("Soap4","88016","ST02","ST02-0001"),
    ("Soap5","88017","ST02","ST02-0002"),
    ("Soap6","88018","ST02","ST02-0003"),
    ("Soap8","88019","ST03","ST03-0001"),
    ("Soap9","88020","ST03","ST03-0002"),
    ("Soap10","88021","ST03","ST03-0003"),
]

for name, code, stype, bin in products:
    db.add(Product(
        product_name=name,
        product_code=code,
        storage_type=stype,
        source_bin=bin
    ))


# ----------- STORAGE BINS -----------
bins = [
    "ST01-0001","ST01-0002","ST01-0003","ST01-0004",
    "ST02-0001","ST02-0002","ST02-0003","ST02-0004",
    "ST03-0001","ST03-0002","ST03-0003","ST03-0004",
    "ST03-0005","ST03-0006","ST03-0007","ST03-0008",
]

for b in bins:
    db.add(StorageBin(bin_code=b, capacity=1000, current_qty=1000))


db.commit()
db.close()

print("✅ Seed data inserted")
