import sqlite3

conn = sqlite3.connect('C:/TESSR-LOGIC/backend/tessr_logic.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print("Tables found:", tables)

# Clear data from each table (but keep table structure)
for table in tables:
    cursor.execute(f"DELETE FROM {table}")
    print(f"Cleared table: {table}")

conn.commit()
conn.close()
print("Database cleared - all old builds removed")
