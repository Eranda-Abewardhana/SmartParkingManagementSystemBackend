import math
import random
import string
from datetime import date, time, datetime, timedelta

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
from models.cameras import Camera

from schemas.users import UserRole
from schemas.vehicles import VehicleType
from schemas.zones import ZoneType
from schemas.reservations import ReservationStatus


def generate_slots_for_capacity(capacity: int):
    """
    Generate slot labels like A1, A2, ..., B1, B2...
    Uses up to 4 columns per row to keep labels clean.
    """
    if capacity <= 0:
        return []

    cols = 4
    rows = math.ceil(capacity / cols)
    letters = string.ascii_uppercase

    slots = []
    for r in range(rows):
        for c in range(1, cols + 1):
            if len(slots) >= capacity:
                break
            slots.append(f"{letters[r]}{c}")
    return slots


def pick_slot_map(zones):
    """
    Build {zone_id: [slot labels]} for quick realistic slot assignment.
    """
    slot_map = {}
    for zone in zones:
        slot_map[zone.id] = generate_slots_for_capacity(zone.capacity)
    return slot_map


def seed_data():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # =========================================================
        # 1. UNIVERSITY MEMBERS
        # =========================================================
        if db.query(UniversityMember).count() == 0:
            print("Seeding university members...")
            members = [
                UniversityMember(
                    university_id="UOC-ST-2026-001",
                    full_name="Nuwan Perera",
                    email="nuwan.perera@uoc.edu",
                    official_role="student",
                    is_active=True,
                ),
                UniversityMember(
                    university_id="UOC-ST-2026-002",
                    full_name="Kavindi Silva",
                    email="kavindi.silva@uoc.edu",
                    official_role="student",
                    is_active=True,
                ),
                UniversityMember(
                    university_id="UOC-ST-2026-003",
                    full_name="Tharindu Fernando",
                    email="tharindu.fernando@uoc.edu",
                    official_role="student",
                    is_active=True,
                ),
                UniversityMember(
                    university_id="UOC-ST-2026-004",
                    full_name="Dinithi Jayasekara",
                    email="dinithi.jayasekara@uoc.edu",
                    official_role="student",
                    is_active=True,
                ),
                UniversityMember(
                    university_id="UOC-SF-2026-001",
                    full_name="Dr. Asanka Wijeratne",
                    email="asanka.wijeratne@uoc.edu",
                    official_role="staff",
                    is_active=True,
                ),
                UniversityMember(
                    university_id="UOC-SF-2026-002",
                    full_name="Prof. Malini De Alwis",
                    email="malini.dealwis@uoc.edu",
                    official_role="staff",
                    is_active=True,
                ),
                UniversityMember(
                    university_id="UOC-SF-2026-003",
                    full_name="Mr. Ravi Gunasekara",
                    email="ravi.gunasekara@uoc.edu",
                    official_role="staff",
                    is_active=True,
                ),
                UniversityMember(
                    university_id="UOC-VS-2026-001",
                    full_name="Saman Kumara",
                    email="saman.kumara.visitor@uoc.edu",
                    official_role="visitor",
                    is_active=True,
                ),
            ]
            db.add_all(members)
            db.commit()

        # =========================================================
        # 2. USERS
        # =========================================================
        if db.query(User).count() == 0:
            print("Seeding users...")
            users = [
                User(
                    username="admin",
                    email="admin@smartparking.lk",
                    full_name="System Administrator",
                    password=hash_password("admin123"),
                    role=UserRole.ADMIN.value,
                    is_active=True,
                ),
                User(
                    username="nuwanp",
                    email="nuwan.perera@uoc.edu",
                    full_name="Nuwan Perera",
                    password=hash_password("student123"),
                    university_id="UOC-ST-2026-001",
                    role=UserRole.STUDENT.value,
                    is_active=True,
                ),
                User(
                    username="kavindis",
                    email="kavindi.silva@uoc.edu",
                    full_name="Kavindi Silva",
                    password=hash_password("student123"),
                    university_id="UOC-ST-2026-002",
                    role=UserRole.STUDENT.value,
                    is_active=True,
                ),
                User(
                    username="tharinduf",
                    email="tharindu.fernando@uoc.edu",
                    full_name="Tharindu Fernando",
                    password=hash_password("student123"),
                    university_id="UOC-ST-2026-003",
                    role=UserRole.STUDENT.value,
                    is_active=True,
                ),
                User(
                    username="dinithij",
                    email="dinithi.jayasekara@uoc.edu",
                    full_name="Dinithi Jayasekara",
                    password=hash_password("student123"),
                    university_id="UOC-ST-2026-004",
                    role=UserRole.STUDENT.value,
                    is_active=True,
                ),
                User(
                    username="asankaw",
                    email="asanka.wijeratne@uoc.edu",
                    full_name="Dr. Asanka Wijeratne",
                    password=hash_password("staff123"),
                    university_id="UOC-SF-2026-001",
                    role=UserRole.STAFF.value,
                    is_active=True,
                ),
                User(
                    username="malinid",
                    email="malini.dealwis@uoc.edu",
                    full_name="Prof. Malini De Alwis",
                    password=hash_password("staff123"),
                    university_id="UOC-SF-2026-002",
                    role=UserRole.STAFF.value,
                    is_active=True,
                ),
                User(
                    username="ravig",
                    email="ravi.gunasekara@uoc.edu",
                    full_name="Mr. Ravi Gunasekara",
                    password=hash_password("staff123"),
                    university_id="UOC-SF-2026-003",
                    role=UserRole.STAFF.value,
                    is_active=True,
                ),
                User(
                    username="visitor1",
                    email="saman.kumara.visitor@uoc.edu",
                    full_name="Saman Kumara",
                    password=hash_password("visitor123"),
                    university_id="UOC-VS-2026-001",
                    role=UserRole.VISITOR.value,
                    is_active=True,
                ),
            ]
            db.add_all(users)
            db.commit()

        # =========================================================
        # 3. ZONES
        # =========================================================
        if db.query(Zone).count() == 0:
            print("Seeding zones...")
            zones = [
                Zone(
                    name="Student Parking Zone A",
                    code="ST-A",
                    zone_type=ZoneType.STUDENT.value,
                    capacity=24,
                    active=True,
                    blocked=False,
                    description="Main student parking area near the faculty entrance.",
                ),
                Zone(
                    name="Student Parking Zone B",
                    code="ST-B",
                    zone_type=ZoneType.STUDENT.value,
                    capacity=20,
                    active=True,
                    blocked=False,
                    description="Secondary student parking area for overflow vehicles.",
                ),
                Zone(
                    name="Staff Parking Zone",
                    code="SF-A",
                    zone_type=ZoneType.STAFF.value,
                    capacity=16,
                    active=True,
                    blocked=False,
                    description="Reserved parking area for academic and non-academic staff.",
                ),
                Zone(
                    name="Visitor Parking Zone",
                    code="VS-A",
                    zone_type=ZoneType.VISITOR.value,
                    capacity=12,
                    active=True,
                    blocked=False,
                    description="Temporary parking area for campus visitors and guests.",
                ),
                Zone(
                    name="VIP Parking Zone",
                    code="VIP-1",
                    zone_type=ZoneType.VIP.value,
                    capacity=6,
                    active=True,
                    blocked=False,
                    description="Reserved parking for university executives and special guests.",
                ),
                Zone(
                    name="Accessible Parking Zone",
                    code="DS-1",
                    zone_type=ZoneType.DISABLED.value,
                    capacity=4,
                    active=True,
                    blocked=False,
                    description="Accessible parking for authorized users.",
                ),
                Zone(
                    name="Mixed Parking Annex",
                    code="MX-1",
                    zone_type=ZoneType.MIXED.value,
                    capacity=18,
                    active=True,
                    blocked=False,
                    description="Mixed-use parking for peak-hour demand.",
                ),
            ]
            db.add_all(zones)
            db.commit()

        zones = db.query(Zone).all()
        slot_map = pick_slot_map(zones)

        # =========================================================
        # 4. CAMERAS
        # =========================================================
        if db.query(Camera).count() == 0:
            print("Seeding cameras...")
            zone_by_code = {z.code: z for z in zones}

            cameras = [
                Camera(
                    name="Entrance Gate Camera",
                    url="0",
                    zone_id=zone_by_code["ST-A"].id,
                    is_active=True,
                ),
                Camera(
                    name="Student Zone B Camera",
                    url="0",
                    zone_id=zone_by_code["ST-B"].id,
                    is_active=True,
                ),
                Camera(
                    name="Staff Zone Camera",
                    url="0",
                    zone_id=zone_by_code["SF-A"].id,
                    is_active=True,
                ),
                Camera(
                    name="Visitor Zone Camera",
                    url="0",
                    zone_id=zone_by_code["VS-A"].id,
                    is_active=True,
                ),
                Camera(
                    name="Mixed Annex Camera",
                    url="0",
                    zone_id=zone_by_code["MX-1"].id,
                    is_active=True,
                ),
            ]
            db.add_all(cameras)
            db.commit()

        # =========================================================
        # 5. VEHICLES
        # =========================================================
        if db.query(Vehicle).count() == 0:
            print("Seeding vehicles...")
            users = db.query(User).filter(User.role != UserRole.ADMIN.value).all()

            vehicle_seed = {
                "nuwan.perera@uoc.edu": [
                    {
                        "plate_number": "CAB4587",
                        "vehicle_type": VehicleType.CAR.value,
                        "brand": "Toyota",
                        "model": "Corolla",
                        "color": "Silver",
                        "is_primary": True,
                    }
                ],
                "kavindi.silva@uoc.edu": [
                    {
                        "plate_number": "BJR9124",
                        "vehicle_type": VehicleType.BIKE.value,
                        "brand": "Honda",
                        "model": "CBR",
                        "color": "Black",
                        "is_primary": True,
                    }
                ],
                "tharindu.fernando@uoc.edu": [
                    {
                        "plate_number": "CAX6721",
                        "vehicle_type": VehicleType.CAR.value,
                        "brand": "Suzuki",
                        "model": "Alto",
                        "color": "White",
                        "is_primary": True,
                    }
                ],
                "dinithi.jayasekara@uoc.edu": [
                    {
                        "plate_number": "WP-KL-3345",
                        "vehicle_type": VehicleType.BIKE.value,
                        "brand": "Yamaha",
                        "model": "FZ",
                        "color": "Blue",
                        "is_primary": True,
                    }
                ],
                "asanka.wijeratne@uoc.edu": [
                    {
                        "plate_number": "CAA7789",
                        "vehicle_type": VehicleType.CAR.value,
                        "brand": "Honda",
                        "model": "Vezel",
                        "color": "Gray",
                        "is_primary": True,
                    }
                ],
                "malini.dealwis@uoc.edu": [
                    {
                        "plate_number": "CAR5501",
                        "vehicle_type": VehicleType.CAR.value,
                        "brand": "Toyota",
                        "model": "Aqua",
                        "color": "Red",
                        "is_primary": True,
                    }
                ],
                "ravi.gunasekara@uoc.edu": [
                    {
                        "plate_number": "NC9921",
                        "vehicle_type": VehicleType.VAN.value,
                        "brand": "Nissan",
                        "model": "Vanette",
                        "color": "White",
                        "is_primary": True,
                    }
                ],
                "saman.kumara.visitor@uoc.edu": [
                    {
                        "plate_number": "PB7844",
                        "vehicle_type": VehicleType.CAR.value,
                        "brand": "Perodua",
                        "model": "Axia",
                        "color": "Silver",
                        "is_primary": True,
                    }
                ],
            }

            vehicles = []
            for user in users:
                for v in vehicle_seed.get(user.email, []):
                    vehicles.append(
                        Vehicle(
                            owner_user_id=user.id,
                            plate_number=v["plate_number"],
                            vehicle_type=v["vehicle_type"],
                            brand=v["brand"],
                            model=v["model"],
                            color=v["color"],
                            is_primary=v["is_primary"],
                            is_active=True,
                        )
                    )

            db.add_all(vehicles)
            db.commit()

        vehicles = db.query(Vehicle).all()
        users = db.query(User).all()
        zones = db.query(Zone).all()

        zone_by_code = {z.code: z for z in zones}
        vehicle_by_plate = {v.plate_number: v for v in vehicles}
        user_by_email = {u.email: u for u in users}

        # =========================================================
        # 6. USER PREFERENCES (OPTIONAL, SAFE SEED)
        # =========================================================
        if db.query(UserPreference).count() == 0:
            print("Seeding user preferences...")
            preferences = []
            normal_users = [u for u in users if u.role != UserRole.ADMIN.value]

            for user in normal_users:
                preferences.append(
                    UserPreference(
                        user_id=user.id,
                        notifications_enabled=True,
                    )
                )
            db.add_all(preferences)
            db.commit()

        # =========================================================
        # 7. RESERVATIONS
        # =========================================================
        if db.query(Reservation).count() == 0:
            print("Seeding reservations...")

            reservation_seed = [
                {
                    "email": "nuwan.perera@uoc.edu",
                    "plate": "CAB4587",
                    "zone_code": "ST-A",
                    "slot": "A1",
                    "day_offset": 0,
                    "start": time(8, 0),
                    "end": time(16, 0),
                    "status": ReservationStatus.OCCUPIED.value,
                    "notes": "Morning lecture parking.",
                },
                {
                    "email": "kavindi.silva@uoc.edu",
                    "plate": "BJR9124",
                    "zone_code": "ST-B",
                    "slot": "A2",
                    "day_offset": 0,
                    "start": time(9, 0),
                    "end": time(14, 0),
                    "status": ReservationStatus.RESERVED.value,
                    "notes": "Reserved for lab session.",
                },
                {
                    "email": "tharindu.fernando@uoc.edu",
                    "plate": "CAX6721",
                    "zone_code": "ST-A",
                    "slot": "A3",
                    "day_offset": 1,
                    "start": time(7, 30),
                    "end": time(12, 30),
                    "status": ReservationStatus.RESERVED.value,
                    "notes": "Reserved for tomorrow morning classes.",
                },
                {
                    "email": "dinithi.jayasekara@uoc.edu",
                    "plate": "WP-KL-3345",
                    "zone_code": "MX-1",
                    "slot": "A1",
                    "day_offset": 1,
                    "start": time(10, 0),
                    "end": time(15, 0),
                    "status": ReservationStatus.PENDING.value,
                    "notes": "Pending approval for mixed zone allocation.",
                },
                {
                    "email": "asanka.wijeratne@uoc.edu",
                    "plate": "CAA7789",
                    "zone_code": "SF-A",
                    "slot": "A1",
                    "day_offset": 0,
                    "start": time(8, 0),
                    "end": time(17, 0),
                    "status": ReservationStatus.OCCUPIED.value,
                    "notes": "Full workday parking.",
                },
                {
                    "email": "malini.dealwis@uoc.edu",
                    "plate": "CAR5501",
                    "zone_code": "VIP-1",
                    "slot": "A1",
                    "day_offset": 0,
                    "start": time(8, 30),
                    "end": time(18, 0),
                    "status": ReservationStatus.RESERVED.value,
                    "notes": "Reserved for department meeting.",
                },
                {
                    "email": "ravi.gunasekara@uoc.edu",
                    "plate": "NC9921",
                    "zone_code": "SF-A",
                    "slot": "A2",
                    "day_offset": -1,
                    "start": time(8, 0),
                    "end": time(16, 0),
                    "status": ReservationStatus.EXPIRED.value,
                    "notes": "Yesterday's completed staff parking.",
                },
                {
                    "email": "saman.kumara.visitor@uoc.edu",
                    "plate": "PB7844",
                    "zone_code": "VS-A",
                    "slot": "A1",
                    "day_offset": 0,
                    "start": time(11, 0),
                    "end": time(13, 0),
                    "status": ReservationStatus.RESERVED.value,
                    "notes": "Visitor meeting reservation.",
                },
            ]

            reservations = []
            for item in reservation_seed:
                user = user_by_email[item["email"]]
                vehicle = vehicle_by_plate[item["plate"]]
                zone = zone_by_code[item["zone_code"]]

                # fallback if slot is not valid for the zone
                valid_slots = slot_map.get(zone.id, [])
                slot_number = item["slot"] if item["slot"] in valid_slots else (
                    valid_slots[0] if valid_slots else "A1"
                )

                reservations.append(
                    Reservation(
                        user_id=user.id,
                        vehicle_id=vehicle.id,
                        zone_id=zone.id,
                        reservation_date=date.today() + timedelta(days=item["day_offset"]),
                        start_time=item["start"],
                        end_time=item["end"],
                        status=item["status"],
                        notes=item["notes"],
                        slot_number=slot_number,
                    )
                )

            db.add_all(reservations)
            db.commit()

        reservations = db.query(Reservation).all()

        # =========================================================
        # 8. ENTRY / EXIT LOGS
        # =========================================================
        if db.query(EntryExitLog).count() == 0:
            print("Seeding entry/exit logs...")

            now = datetime.now()
            reservation_by_vehicle = {}
            for r in reservations:
                reservation_by_vehicle.setdefault(r.vehicle_id, []).append(r)

            logs = [
                EntryExitLog(
                    plate_number="CAB4587",
                    vehicle_id=vehicle_by_plate["CAB4587"].id,
                    user_id=vehicle_by_plate["CAB4587"].owner_user_id,
                    reservation_id=next(
                        (r.id for r in reservations if r.vehicle_id == vehicle_by_plate["CAB4587"].id),
                        None
                    ),
                    gate_type="entry",
                    timestamp=now - timedelta(hours=3, minutes=20),
                    source="Entrance Gate Camera",
                    status="matched",
                    is_overstayed=False,
                    notes="Student vehicle entered successfully.",
                ),
                EntryExitLog(
                    plate_number="CAA7789",
                    vehicle_id=vehicle_by_plate["CAA7789"].id,
                    user_id=vehicle_by_plate["CAA7789"].owner_user_id,
                    reservation_id=next(
                        (r.id for r in reservations if r.vehicle_id == vehicle_by_plate["CAA7789"].id),
                        None
                    ),
                    gate_type="entry",
                    timestamp=now - timedelta(hours=2, minutes=40),
                    source="Staff Zone Camera",
                    status="matched",
                    is_overstayed=False,
                    notes="Staff vehicle entered with valid reservation.",
                ),
                EntryExitLog(
                    plate_number="PB7844",
                    vehicle_id=vehicle_by_plate["PB7844"].id,
                    user_id=vehicle_by_plate["PB7844"].owner_user_id,
                    reservation_id=next(
                        (r.id for r in reservations if r.vehicle_id == vehicle_by_plate["PB7844"].id),
                        None
                    ),
                    gate_type="entry",
                    timestamp=now - timedelta(hours=1, minutes=15),
                    source="Visitor Zone Camera",
                    status="matched",
                    is_overstayed=False,
                    notes="Visitor entered for scheduled meeting.",
                ),
                EntryExitLog(
                    plate_number="BJR9124",
                    vehicle_id=vehicle_by_plate["BJR9124"].id,
                    user_id=vehicle_by_plate["BJR9124"].owner_user_id,
                    reservation_id=next(
                        (r.id for r in reservations if r.vehicle_id == vehicle_by_plate["BJR9124"].id),
                        None
                    ),
                    gate_type="entry",
                    timestamp=now - timedelta(minutes=55),
                    source="Student Zone B Camera",
                    status="matched",
                    is_overstayed=False,
                    notes="Bike entered with active reservation.",
                ),
                EntryExitLog(
                    plate_number="XYZ0000",
                    vehicle_id=None,
                    user_id=None,
                    reservation_id=None,
                    gate_type="entry",
                    timestamp=now - timedelta(minutes=30),
                    source="Entrance Gate Camera",
                    status="unmatched",
                    is_overstayed=False,
                    notes="Unknown plate detected at entry.",
                ),
                EntryExitLog(
                    plate_number="NC9921",
                    vehicle_id=vehicle_by_plate["NC9921"].id,
                    user_id=vehicle_by_plate["NC9921"].owner_user_id,
                    reservation_id=next(
                        (r.id for r in reservations if r.vehicle_id == vehicle_by_plate["NC9921"].id),
                        None
                    ),
                    gate_type="exit",
                    timestamp=now - timedelta(hours=18),
                    source="Staff Zone Camera",
                    status="matched",
                    is_overstayed=False,
                    notes="Vehicle exited after yesterday reservation.",
                ),
            ]

            db.add_all(logs)
            db.commit()

        # =========================================================
        # 9. LPR DETECTIONS
        # =========================================================
        if db.query(LprDetection).count() == 0:
            print("Seeding LPR detections...")
            detections = [
                LprDetection(
                    detected_plate="CAB4587",
                    confidence=0.98,
                    source_camera="Entrance Gate Camera",
                    detected_at=datetime.now() - timedelta(minutes=15),
                    review_status="approved",
                ),
                LprDetection(
                    detected_plate="CAA7789",
                    confidence=0.97,
                    source_camera="Staff Zone Camera",
                    detected_at=datetime.now() - timedelta(minutes=18),
                    review_status="approved",
                ),
                LprDetection(
                    detected_plate="PB7844",
                    confidence=0.94,
                    source_camera="Visitor Zone Camera",
                    detected_at=datetime.now() - timedelta(minutes=25),
                    review_status="pending",
                ),
                LprDetection(
                    detected_plate="BJR9124",
                    confidence=0.91,
                    source_camera="Student Zone B Camera",
                    detected_at=datetime.now() - timedelta(minutes=9),
                    review_status="pending",
                ),
                LprDetection(
                    detected_plate="XYZ0000",
                    confidence=0.86,
                    source_camera="Entrance Gate Camera",
                    detected_at=datetime.now() - timedelta(minutes=5),
                    review_status="pending",
                ),
            ]
            db.add_all(detections)
            db.commit()

        # =========================================================
        # 10. NOTIFICATIONS
        # =========================================================
        if db.query(Notification).count() == 0:
            print("Seeding notifications...")

            normal_users = [u for u in users if u.role != UserRole.ADMIN.value]
            notifications = []

            notification_templates = [
                ("Reservation Confirmed", "Your parking reservation has been confirmed.", "reservation"),
                ("Vehicle Entry Logged", "Your vehicle entry has been recorded successfully.", "entry"),
                ("Vehicle Exit Logged", "Your vehicle exit has been recorded successfully.", "exit"),
                ("Zone Alert", "A parking zone is reaching capacity.", "alert"),
                ("System Notice", "System maintenance is scheduled for tonight.", "system"),
            ]

            for i, user in enumerate(normal_users):
                title, message, ntype = notification_templates[i % len(notification_templates)]
                notifications.append(
                    Notification(
                        user_id=user.id,
                        title=title,
                        message=message,
                        type=ntype,
                        is_read=(i % 2 == 0),
                        created_at=datetime.now() - timedelta(hours=i + 1),
                    )
                )

            # Admin notifications
            admin_user = next((u for u in users if u.role == UserRole.ADMIN.value), None)
            if admin_user:
                notifications.extend([
                    Notification(
                        user_id=admin_user.id,
                        title="Unmatched LPR Detection",
                        message="An unmatched vehicle plate was detected at the entrance gate.",
                        type="alert",
                        is_read=False,
                        created_at=datetime.now() - timedelta(minutes=20),
                    ),
                    Notification(
                        user_id=admin_user.id,
                        title="Daily Parking Summary Ready",
                        message="Today's parking dashboard summary is now available.",
                        type="system",
                        is_read=False,
                        created_at=datetime.now() - timedelta(minutes=10),
                    ),
                ])

            db.add_all(notifications)
            db.commit()

        # =========================================================
        # 11. OCCUPANCY SNAPSHOTS
        # =========================================================
        if db.query(OccupancySnapshot).count() == 0:
            print("Seeding occupancy snapshots...")

            occupancy_seed = [
                ("ST-A", 8, "camera"),
                ("ST-B", 5, "system"),
                ("SF-A", 6, "camera"),
                ("VS-A", 3, "manual"),
                ("VIP-1", 2, "system"),
                ("DS-1", 1, "manual"),
                ("MX-1", 4, "camera"),
            ]

            snapshots = []
            for zone_code, occupied_count, source in occupancy_seed:
                zone = zone_by_code[zone_code]
                snapshots.append(
                    OccupancySnapshot(
                        zone_id=zone.id,
                        occupied_count=min(occupied_count, zone.capacity),
                        updated_at=datetime.now() - timedelta(minutes=random.randint(1, 30)),
                        source=source,
                    )
                )

            db.add_all(snapshots)
            db.commit()

        print("Database seeding completed successfully with realistic data!")

    except Exception as e:
        print(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()