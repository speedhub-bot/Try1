import json
import os

DB_FILE = "users.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"admin": 5944410248, "users": {}}
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"admin": 5944410248, "users": {}}

def save_db(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def is_admin(user_id):
    db = load_db()
    return user_id == db.get("admin")

def is_banned(user_id):
    db = load_db()
    user = db["users"].get(str(user_id))
    return user and user.get("banned", False)

def is_approved(user_id):
    if is_admin(user_id):
        return True
    if is_banned(user_id):
        return False
    db = load_db()
    user = db["users"].get(str(user_id))
    return user and user.get("approved", False)

def get_credits(user_id):
    if is_admin(user_id):
        return 999999
    db = load_db()
    user = db["users"].get(str(user_id))
    return user.get("credits", 0) if user else 0

def add_credits(user_id, amount):
    db = load_db()
    user_id_str = str(user_id)
    if user_id_str not in db["users"]:
        db["users"][user_id_str] = {"approved": False, "credits": 0, "threads": 5, "proxy_file": None, "plan": "Free", "banned": False}
    db["users"][user_id_str]["credits"] += amount
    save_db(db)

def set_approved(user_id, status):
    db = load_db()
    user_id_str = str(user_id)
    if user_id_str not in db["users"]:
        db["users"][user_id_str] = {"approved": False, "credits": 0, "threads": 5, "proxy_file": None, "plan": "Free", "banned": False}
    db["users"][user_id_str]["approved"] = status
    save_db(db)

def ban_user(user_id):
    db = load_db()
    user_id_str = str(user_id)
    if user_id_str not in db["users"]:
        db["users"][user_id_str] = {"approved": False, "credits": 0, "threads": 5, "proxy_file": None, "plan": "Free", "banned": False}
    db["users"][user_id_str]["banned"] = True
    save_db(db)

def unban_user(user_id):
    db = load_db()
    user_id_str = str(user_id)
    if user_id_str in db["users"]:
        db["users"][user_id_str]["banned"] = False
        save_db(db)

def set_plan(user_id, plan_name):
    db = load_db()
    user_id_str = str(user_id)
    if user_id_str not in db["users"]:
        db["users"][user_id_str] = {"approved": False, "credits": 0, "threads": 5, "proxy_file": None, "plan": "Free", "banned": False}
    db["users"][user_id_str]["plan"] = plan_name
    save_db(db)

def get_plan(user_id):
    if is_admin(user_id):
        return "Owner"
    db = load_db()
    user = db["users"].get(str(user_id))
    return user.get("plan", "Free") if user else "Free"

def deduct_credit(user_id):
    if is_admin(user_id):
        return True
    db = load_db()
    user_id_str = str(user_id)
    user = db["users"].get(user_id_str)
    if user and user.get("credits", 0) > 0:
        db["users"][user_id_str]["credits"] -= 1
        save_db(db)
        return True
    return False

def get_user_settings(user_id):
    db = load_db()
    user_id_str = str(user_id)
    user = db["users"].get(user_id_str)
    if not user:
        if is_admin(user_id):
             return {"threads": 50, "proxy_file": None}
        return {"threads": 5, "proxy_file": None}
    return {
        "threads": user.get("threads", 5),
        "proxy_file": user.get("proxy_file")
    }

def update_user_settings(user_id, threads=None, proxy_file=None):
    db = load_db()
    user_id_str = str(user_id)
    if user_id_str not in db["users"]:
        db["users"][user_id_str] = {"approved": False, "credits": 0, "threads": 5, "proxy_file": None, "plan": "Free", "banned": False}

    if threads is not None:
        db["users"][user_id_str]["threads"] = threads
    if proxy_file is not None:
        db["users"][user_id_str]["proxy_file"] = proxy_file if proxy_file else None

    save_db(db)

def get_all_users():
    db = load_db()
    return db["users"]
