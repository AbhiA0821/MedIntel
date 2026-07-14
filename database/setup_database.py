import duckdb

con = duckdb.connect("database/medintel.duckdb")

with open("database/schema.sql", "r") as file:
    schema = file.read()

con.execute(schema)

print("Database and tables created successfully!")

con.close()