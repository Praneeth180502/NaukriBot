import sqlite3
import os

db_path = 'data/job_hunter.db'
if not os.path.exists(db_path):
    print("No DB found")
    exit()

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print('Tables:', tables)
    for table in tables:
        t = table[0]
        cursor.execute(f'SELECT * FROM {t}')
        rows = cursor.fetchall()
        for row in rows:
            if '1.3' in str(row):
                print(f'Found 1.3 in table {t}:', row)
except Exception as e:
    print('DB error:', e)
