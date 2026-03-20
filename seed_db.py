from core.database import SessionLocal, engine, Base
from core.security import hash_password
from models.users import User
from models.vehicles import Vehicle
from models.zones import Zone
from models.reservations import Reservation
from models.university import UniversityMember
from schemas.users import UserRole
from schemas.vehicles import VehicleType
from schemas.zones import ZoneType
from datetime import date, time, datetime

def seed_data():
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # 1. Seed University Members (Official Mock Database)
        if db.query(UniversityMember).count() == 0:
            print("Seeding university members...")
            members = [
                UniversityMember(
                    university_id="UOC-ST-001",
                    full_name="John Student",
                    email="student1@uoc.edu",
                    official_role="student",
                    is_active=True
                ),
                UniversityMember(
                    university_id="UOC-ST-002",
                    full_name="Jane Student",
                    email="student2@uoc.edu",
                    official_role="student",
                    is_active=True
                ),
                UniversityMember(
                    university_id="UOC-SF-001",
                    full_name="Dr. Smith",
                    email="staff1@uoc.edu",
                    official_role="staff",
                    is_active=True
                ),
            ]
            db.add_all(members)
            db.commit()

        # 2. Seed Users
        if db.query(User).count() == 0:
            print("Seeding users...")
            admin = User(
                username="admin",
                email="admin@uoc.edu",
                full_name="System Administrator",
                password=hash_password("admin123"),
                role="admin",
                is_active=True
            )
            student = User(
                username="student1",
                email="student1@uoc.edu",
                full_name="John Student",
                password=hash_password("student123"),
                university_id="UOC-ST-001",
                role="student",
                is_active=True
            )
            staff = User(
                username="staff1",
                email="staff1@uoc.edu",
                full_name="Dr. Smith",
                password=hash_password("staff123"),
                university_id="UOC-SF-001",
                role="staff",
                is_active=True
            )
            db.add_all([admin, student, staff])
            db.commit()

        # 3. Seed Zones
        if db.query(Zone).count() == 0:
            print("Seeding zones...")
            zones = [
                Zone(name="Student Zone A", code="STU-A", zone_type="student", capacity=50, active=True, blocked=False, description="Main student parking area."),
                Zone(name="Staff Zone B", code="STF-B", zone_type="staff", capacity=20, active=True, blocked=False, description="Reserved for academic staff."),
                Zone(name="Visitor Zone C", code="VIS-C", zone_type="visitor", capacity=10, active=True, blocked=False, description="Temporary visitor parking."),
            ]
            db.add_all(zones)
            db.commit()

        # 4. Seed Vehicles (link to student)
        if db.query(Vehicle).count() == 0:
            print("Seeding vehicles...")
            student_user = db.query(User).filter(User.username == "student1").first()
            if student_user:
                v1 = Vehicle(
                    owner_user_id=student_user.id,
                    plate_number="CAB-1234",
                    vehicle_type="car",
                    brand="Toyota",
                    model="Vitz",
                    color="White",
                    is_primary=True,
                    is_active=True
                )
                v2 = Vehicle(
                    owner_user_id=student_user.id,
                    plate_number="BKE-9001",
                    vehicle_type="bike",
                    brand="Honda",
                    model="CBR",
                    color="Black",
                    is_primary=False,
                    is_active=True
                )
                db.add_all([v1, v2])
                db.commit()

        # 5. Seed a Reservation
        if db.query(Reservation).count() == 0:
            print("Seeding reservations...")
            student_user = db.query(User).filter(User.username == "student1").first()
            vehicle = db.query(Vehicle).filter(Vehicle.plate_number == "CAB-1234").first()
            zone = db.query(Zone).filter(Zone.code == "STU-A").first()
            
            if student_user and vehicle and zone:
                res = Reservation(
                    user_id=student_user.id,
                    vehicle_id=vehicle.id,
                    zone_id=zone.id,
                    reservation_date=date.today(),
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                    status="confirmed",
                    notes="Daily parking"
                )
                db.add(res)
                db.commit()

        print("Database seeding completed successfully!")
    except Exception as e:
        print(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
