import sqlite3
db = sqlite3.connect(r"G:\openclaw\DocMind\backend\docmind.db")

# Check token_usages user_id
rows = db.execute("SELECT user_id FROM token_usages").fetchall()
for r in rows:
    match = db.execute(f"SELECT username FROM users WHERE id='{r[0]}'").fetchone()
    print(f"token user_id {r[0]} -> {match[0] if match else 'NO MATCH'}")

print()
print("Users with 0 token records:")
all_users = db.execute("SELECT id, username FROM users").fetchall()
for uid, uname in all_users:
    has_token = db.execute(f"SELECT COUNT(*) FROM token_usages WHERE user_id='{uid}'").fetchone()[0]
    print(f"  {uname}: {has_token} token records")
