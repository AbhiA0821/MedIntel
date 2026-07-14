import duckdb

# Connect to the database
con = duckdb.connect("database/medintel.duckdb")

# Read the SQL file
with open("database/vital_signs_data.sql", "r") as file:
    sql = file.read()

# Execute the INSERT statements
con.execute(sql)

print("Vital signs inserted successfully!")

# Close the connection
con.close()