from core.database import engine, Base
import seed_db

def reset_and_seed():
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Recreating all tables and seeding...")
    seed_db.seed_data()

if __name__ == "__main__":
    reset_and_seed()
