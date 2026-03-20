# Smart Parking Management API

A FastAPI-based backend prototype for a Smart Parking Management System. This project is designed for a university parking scenario with zone-based reservations, vehicle tracking, gate event logging, LPR result intake, occupancy monitoring, admin operations, and user notifications.

## Features

### Authentication
- JWT-style auth structure
- Login, logout, current-user profile, token refresh endpoints

### User management
- View current profile
- Update basic profile details
- Admin user listing, role changes, and activation/deactivation

### Vehicle management
- Register vehicles
- Manage vehicle details
- Mark a primary vehicle
- Admin vehicle listing and filtering

### Zone management
- Create and manage parking zones
- View zone availability
- Zone status updates (active/blocked)

### Reservation management
- Zone-based reservation creation
- Reservation listing and history
- Cancel and reschedule reservations
- Admin reservation status updates

### Entry/exit logging
- Entry and exit gate event recording
- Current vehicles inside campus
- Log filtering for admins

### LPR result handling
- Store license plate detections from a Python vision service
- Review and correct unmatched detections
- Link detections to vehicles and reservations

### Occupancy and availability
- Update zone occupancy from camera/manual/system inputs
- View live zone occupancy summaries
- Manual occupancy adjustments

### Admin operations
- Dashboard summary
- Manual entry decisions
- Manual zone reassignment
- Resolve unmatched LPR detections
- Audit log viewing

### Notifications
- User notifications
- Mark one or all notifications as read
- Admin notification listing

## Project structure

```text
app/
  main.py
  routers/
    auth.py
    users.py
    vehicles.py
    zones.py
    reservations.py
    entry_exit_logs.py
    lpr.py
    occupancy.py
    admin.py
    notifications.py
  schemas/
    auth.py
    users.py
    vehicles.py
    zones.py
    reservations.py
    entry_exit_logs.py
    lpr.py
    occupancy.py
    admin.py
    notifications.py
```

## Requirements

Use the following in `requirements.txt`:

```txt
fastapi>=0.115.0,<1.0.0
uvicorn[standard]>=0.30.0,<1.0.0
pydantic>=2.8.0,<3.0.0
python-jose[cryptography]>=3.3.0,<4.0.0
sqlalchemy>=2.0.0,<3.0.0
psycopg2-binary>=2.9.0,<3.0.0
python-multipart>=0.0.9,<1.0.0
email-validator>=2.2.0,<3.0.0
```

## Installation

Create and activate a virtual environment, then install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the project

Start the FastAPI development server:

```bash
uvicorn app.main:app --reload
```

The API will be available at:
- `http://127.0.0.1:8000`
- Swagger docs: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Available routers

The application registers these routers:
- `/auth`
- `/users`
- `/vehicles`
- `/zones`
- `/reservations`
- `/entry-exit`
- `/lpr`
- `/occupancy`
- `/admin`
- `/notifications`

## Root and health endpoints

- `GET /` returns a simple API message
- `GET /health` returns service health status

## Current implementation notes

This version is a **prototype backend**.

A number of modules currently use:
- in-memory placeholder data stores
- placeholder auth dependencies
- TODO markers for service/repository/database integration

That means this project is suitable for:
- API structure design
- frontend/mobile integration
- demo and prototype workflows
- gradual migration to PostgreSQL and SQLAlchemy models

It is not yet production-ready.

## Next recommended steps

1. Replace in-memory fake databases with SQLAlchemy models
2. Add a real PostgreSQL database connection
3. Implement JWT creation and verification centrally
4. Move business logic into service layers
5. Add repository/database access layers
6. Add unit and integration tests
7. Connect the LPR Python vision service
8. Connect frontend and mobile clients

## Example startup checklist

- Create project folders
- Add all router and schema files
- Add `main.py`
- Add `requirements.txt`
- Install dependencies
- Run `uvicorn app.main:app --reload`
- Open `/docs` and test endpoints

## Notes for prototype usage

For a one-week prototype, this backend is already structured well for:
- admin web dashboard integration
- user mobile app integration
- phone-camera-based gate and parking workflows
- mocked or incremental AI integration

## License

This repository is currently for academic/project prototype use.

