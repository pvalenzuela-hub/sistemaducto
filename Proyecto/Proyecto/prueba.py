import pyodbc

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=72.60.59.142,1433;"
    "DATABASE=project;"
    "UID=ducto_user;"
    "PWD=sqL_2025!###;"
    "TrustServerCertificate=yes;"
)

print("Conexión OK")
