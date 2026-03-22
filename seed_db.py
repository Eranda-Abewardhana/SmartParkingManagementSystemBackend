from core.database import SessionLocal, engine, Base
from core.security import hash_password

# Import ALL models so SQLAlchemy registers them with Base.metadata before create_all
from models.users import User
from models.vehicles import Vehicle
from models.zones import Zone
from models.reservations import Reservation
from models.university import UniversityMember
from models.preferences import UserPreference
from models.auth import PasswordResetCode
from models.lpr import LprDetection
from models.notifications import Notification
from models.entry_exit_logs import EntryExitLog
from models.occupancy import OccupancySnapshot

from schemas.users import UserRole
from schemas.vehicles import VehicleType
from schemas.zones import ZoneType
from datetime import date, time, datetime, timedelta
import random


def seed_data():
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 1. Seed University Members
        if db.query(UniversityMember).count() == 0:
            print("Seeding university members...")
            members = [
                UniversityMember(university_id="UOC-ST-001", full_name="John Student", email="student1@uoc.edu",
                                 official_role="student", is_active=True),
                UniversityMember(university_id="UOC-ST-002", full_name="Jane Doe", email="student2@uoc.edu",
                                 official_role="student", is_active=True),
                UniversityMember(university_id="UOC-SF-001", full_name="Dr. Smith", email="staff1@uoc.edu",
                                 official_role="staff", is_active=True),
                UniversityMember(university_id="UOC-SF-002", full_name="Prof. Johnson", email="staff2@uoc.edu",
                                 official_role="staff", is_active=True),
                UniversityMember(university_id="UOC-ST-003", full_name="Alice Wong", email="student3@uoc.edu",
                                 official_role="student", is_active=True),
                UniversityMember(university_id="UOC-SF-003", full_name="Sarah Miller", email="staff3@uoc.edu",
                                 official_role="staff", is_active=True),
            ]
            db.add_all(members)
            db.commit()

        # 2. Seed Users
        if db.query(User).count() == 0:
            print("Seeding users...")
            users = [
                User(username="admin", email="admin@uoc.edu", full_name="System Admin",
                     password=hash_password("admin123"), role="admin", is_active=True),
                User(username="student1", email="student1@uoc.edu", full_name="John Student",
                     password=hash_password("student123"), university_id="UOC-ST-001", role="student", is_active=True),
                User(username="student2", email="student2@uoc.edu", full_name="Jane Doe",
                     password=hash_password("student123"), university_id="UOC-ST-002", role="student", is_active=True),
                User(username="staff1", email="staff1@uoc.edu", full_name="Dr. Smith",
                     password=hash_password("staff123"), university_id="UOC-SF-001", role="staff", is_active=True),
                User(username="staff2", email="staff2@uoc.edu", full_name="Prof. Johnson",
                     password=hash_password("staff123"), university_id="UOC-SF-002", role="staff", is_active=True),
            ]
            db.add_all(users)
            db.commit()

        # 3. Seed Zones
        if db.query(Zone).count() == 0:
            print("Seeding zones...")
            zones = [
                Zone(name="Main Entrance A", code="ENT-A", zone_type="student", capacity=50, active=True, blocked=False,
                     description="Primary student parking."),
                Zone(name="Faculty Wing B", code="FAC-B", zone_type="staff", capacity=30, active=True, blocked=False,
                     description="Reserved for staff."),
                Zone(name="Visitor Lot C", code="VIS-C", zone_type="visitor", capacity=15, active=True, blocked=False,
                     description="Temporary visitor parking."),
                Zone(name="Overflow North", code="OVF-N", zone_type="student", capacity=100, active=True, blocked=False,
                     description="North side overflow."),
                Zone(name="VIP Reserved", code="VIP-S", zone_type="staff", capacity=10, active=True, blocked=False,
                     description="Senior staff parking."),
            ]
            db.add_all(zones)
            db.commit()

        # 4. Seed Vehicles
        if db.query(Vehicle).count() == 0:
            print("Seeding vehicles...")
            all_users = db.query(User).filter(User.role != "admin").all()
            plates = ["CAB-1234", "WP-BKE-9001", "CAR-5566", "SUV-7788", "VAN-1122", "TRK-4433"]
            brands = ["Toyota", "Honda", "Nissan", "Tesla", "Ford", "BMW"]
            models = ["Corolla", "Civic", "Leaf", "Model 3", "F-150", "X5"]

            vehicles = []
            for i, user in enumerate(all_users):
                vehicles.append(Vehicle(
                    owner_user_id=user.id,
                    plate_number=plates[i % len(plates)],
                    vehicle_type="car" if i % 2 == 0 else "bike",
                    brand=brands[i % len(brands)],
                    model=models[i % len(models)],
                    color="Silver",
                    is_primary=True,
                    is_active=True
                ))
            db.add_all(vehicles)
            db.commit()

        # 5. Seed Reservations
        if db.query(Reservation).count() == 0:
            print("Seeding reservations...")
            vehicles = db.query(Vehicle).all()
            zones = db.query(Zone).all()

            reservations = []
            statuses = ["confirmed", "pending", "completed", "cancelled", "expired"]
            for i in range(10):
                res = Reservation(
                    user_id=vehicles[i % len(vehicles)].owner_user_id,
                    vehicle_id=vehicles[i % len(vehicles)].id,
                    zone_id=zones[i % len(zones)].id,
                    reservation_date=date.today() + timedelta(days=random.randint(-2, 5)),
                    start_time=time(random.randint(7, 10), 0),
                    end_time=time(random.randint(15, 18), 0),
                    status=statuses[i % len(statuses)],
                    notes=f"Test reservation {i + 1}"
                )
                reservations.append(res)
            db.add_all(reservations)
            db.commit()

        # 6. Seed Entry/Exit Logs
        if db.query(EntryExitLog).count() == 0:
            print("Seeding entry/exit logs...")
            vehicles = db.query(Vehicle).all()
            reservations = db.query(Reservation).all()
            logs = []
            for i in range(8):
                logs.append(EntryExitLog(
                    plate_number=vehicles[i % len(vehicles)].plate_number,
                    vehicle_id=vehicles[i % len(vehicles)].id,
                    user_id=vehicles[i % len(vehicles)].owner_user_id,
                    reservation_id=reservations[i % len(reservations)].id if i % 2 == 0 else None,
                    gate_type="entry" if i % 2 == 0 else "exit",
                    timestamp=datetime.now() - timedelta(hours=random.randint(1, 24)),
                    source="Camera-01" if i % 2 == 0 else "Camera-02",
                    status=(
                        "matched" if i % 4 == 0 else
                        "unmatched" if i % 4 == 1 else
                        "manual_override" if i % 4 == 2 else
                        "denied"
                    ),
                    is_overstayed=i % 5 == 0,
                    notes=f"Test log {i + 1}"
                ))
            db.add_all(logs)
            db.commit()

        # 7. Seed LPR Detections
        if db.query(LprDetection).count() == 0:
            print("Seeding LPR detections...")
            plates = ["CAB-1234", "CAR-5566", "UNK-9999", "SUV-7788", "VAN-1122"]
            detections = []
            for plate in plates:
                detections.append(LprDetection(
                    detected_plate=plate,
                    confidence=random.uniform(0.85, 0.99),
                    source_camera=random.choice(["CAM-01", "CAM-02"]),
                    detected_at=datetime.now() - timedelta(minutes=random.randint(1, 120)),
                    review_status="pending"
                ))
            db.add_all(detections)
            db.commit()

        # 8. Seed Notifications
        if db.query(Notification).count() == 0:
            print("Seeding notifications...")
            users = db.query(User).all()
            notifs = []
            for i in range(10):
                notifs.append(Notification(
                    user_id=users[i % len(users)].id,
                    title="System Alert",
                    message=f"Test notification message {i + 1}",
                    type="alert",
                    is_read=i % 2 == 0,
                    created_at=datetime.now() - timedelta(hours=i)
                ))
            db.add_all(notifs)
            db.commit()

        print("Database seeding completed successfully!")
    except Exception as e:
        print(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()