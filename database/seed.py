"""
database/seed.py
-----------------
One-time setup script: creates the database, registers a starting set
of sensor nodes (spread across a hypothetical underground coal mine
panel area), and creates default login users for each role.

Run with:  python database/seed.py
"""

import os
import sys
from werkzeug.security import generate_password_hash

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database.db as db

# Example coordinates loosely centered on a coalfield region in India
# (Jharia coalfield area) purely for a realistic-looking demo map.
DEFAULT_NODES = [
    {"node_id": "NODE_01", "latitude": 23.7401, "longitude": 86.4131, "installation_area": "Panel A - North"},
    {"node_id": "NODE_02", "latitude": 23.7415, "longitude": 86.4160, "installation_area": "Panel A - Center"},
    {"node_id": "NODE_03", "latitude": 23.7392, "longitude": 86.4188, "installation_area": "Panel A - South"},
    {"node_id": "NODE_04", "latitude": 23.7430, "longitude": 86.4145, "installation_area": "Panel B - North"},
    {"node_id": "NODE_05", "latitude": 23.7378, "longitude": 86.4152, "installation_area": "Panel B - South"},
    {"node_id": "NODE_06", "latitude": 23.7408, "longitude": 86.4200, "installation_area": "Panel C - East"},
]

DEFAULT_USERS = [
    {"username": "operator", "password": "operator123", "role": "OPERATOR"},
    {"username": "planner", "password": "planner123", "role": "PLANNER"},
    {"username": "regulator", "password": "regulator123", "role": "REGULATOR"},
]


def seed():
    print("Initializing database schema...")
    db.init_db()

    print("Registering sensor nodes...")
    for node in DEFAULT_NODES:
        db.upsert_node(
            node["node_id"], node["latitude"], node["longitude"],
            installation_area=node["installation_area"], status="ACTIVE",
        )
        print(f"  - {node['node_id']} ({node['installation_area']})")

    print("Creating default users (CHANGE THESE PASSWORDS for any real use)...")
    for u in DEFAULT_USERS:
        if db.get_user_by_username(u["username"]) is None:
            db.create_user(u["username"], generate_password_hash(u["password"]), role=u["role"])
            print(f"  - {u['username']} / role={u['role']}")
        else:
            print(f"  - {u['username']} already exists, skipping")

    print("\nSeed complete. Default login credentials (for demo only):")
    for u in DEFAULT_USERS:
        print(f"  {u['role']:10s} -> username: {u['username']:10s} password: {u['password']}")


if __name__ == "__main__":
    seed()
