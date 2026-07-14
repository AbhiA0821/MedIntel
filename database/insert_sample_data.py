import duckdb

# Connect to the existing database
con = duckdb.connect("database/medintel.duckdb")

# Read the SQL file
with open("database/sample_data.sql", "r") as file:
    sql = file.read()

# Execute all SQL statements
con.execute(sql)

print("Sample data inserted successfully!")

con.close()