import duckdb

con = duckdb.connect("database/medintel.duckdb")

rows = con.execute("""
SELECT *
FROM VitalSigns;
""").fetchall()

for row in rows:
    print(row)

con.close()