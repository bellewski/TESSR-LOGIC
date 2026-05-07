import sqlite3, os
db_path = r'C:\TESSR-LOGIC\tessr_logic.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]
    print('Tables:', tables)
    if 'agent_configs' in tables:
        cursor.execute("SELECT agent_type, length(system_prompt) FROM agent_configs")
        for row in cursor.fetchall():
            print(f'  {row[0]}: {row[1]} chars')
    conn.close()
else:
    print('No DB found')
