import duckdb

def get_connection():
    return duckdb.connect("database/medintel.duckdb")