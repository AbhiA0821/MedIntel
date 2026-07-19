import duckdb

con = duckdb.connect("database/medintel.duckdb")

# Return rows as dictionaries
con.execute("SET python_result_conversion='pandas'")