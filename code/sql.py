import pandas as pd
import sqlite3

csv_path = "data/Amazon Sale Report.csv"
df = pd.read_csv(csv_path)

db_path = "sales.db"
conn = sqlite3.connect(db_path)

df.to_sql(
    name="sales",          # table name
    con=conn,
    if_exists="replace",   # replace or append
    index=False
)

conn.close()