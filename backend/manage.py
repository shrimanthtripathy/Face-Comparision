"""python -m backend.manage create-user NAME --role admin | set-password NAME | delete-user NAME | list-users | verify-audit"""
import argparse, getpass, sys
from . import db as D, registration as R

def ask():
    a = getpass.getpass("Password (12+ characters): "); b = getpass.getpass("Repeat password: ")
    if a != b: sys.exit("Passwords do not match.")
    return a

p = argparse.ArgumentParser(); sp = p.add_subparsers(dest="cmd", required=True)
c = sp.add_parser("create-user"); c.add_argument("username"); c.add_argument("--role", default="examiner", choices=["admin", "examiner"])
for n in ("set-password", "delete-user"): sp.add_parser(n).add_argument("username")
sp.add_parser("list-users"); sp.add_parser("verify-audit"); sp.add_parser("list-operators")
a = p.parse_args()
try:
    if a.cmd == "create-user": D.create_user(a.username, ask(), a.role); print("User created.")
    elif a.cmd == "set-password": D.set_password(a.username, ask()); print("Password updated.")
    elif a.cmd == "delete-user": D.delete_user(a.username); print("User deleted.")
    elif a.cmd == "list-operators":
        for o in R.list_operators(): print(o["created"], o["name"], o["organisation"], o["designation"], o["email"], o["country"], o["purpose"], sep=" | ")
    elif a.cmd == "list-users": [print(u["username"], u["role"]) for u in D.list_users()]
    else:
        ok, bad = D.audit_verify(); print("Audit log intact." if ok else f"TAMPERING DETECTED at entry {bad}"); sys.exit(0 if ok else 1)
except Exception as e:
    sys.exit(str(e))
