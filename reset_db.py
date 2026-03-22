from sqlalchemy import text
from core.database import engine, Base

# ✅ IMPORT ALL MODELS (CRITICAL - ensures metadata is complete)
from models.users import User
from models.vehicles import Vehicle
from models.zones import Zone
from models.reservations import Reservation
from models.university import UniversityMember
from models.occupancy import OccupancySnapshot
from models.entry_exit_logs import EntryExitLog
from models.lpr import LprDetection  # ⚠️ REQUIRED (your missing dependency)
from models.preferences import UserPreference

from seed_db import seed_data


def reset_and_seed():
    # ⚠️ Safety check (VERY IMPORTANT)
    ENV = "dev"  # you can replace this with os.getenv("ENV")
    if ENV != "dev":
        raise Exception("❌ Database reset is blocked outside development environment")

    print("Dropping all tables with CASCADE...")

    # 🔥 Drop all tables with CASCADE (handles FK dependencies)
    with engine.connect() as conn:
        conn.execute(text("""
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (
                    SELECT tablename 
                    FROM pg_tables 
                    WHERE schemaname = 'public'
                ) LOOP
                    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                END LOOP;
            END $$;
        """))
        conn.commit()

    print("Creating tables...")
    Base.metadata.create_all(bind=engine)

    print("Seeding database...")
    seed_data()

    print("✅ Reset and seeding completed successfully!")


if __name__ == "__main__":
    reset_and_seed()