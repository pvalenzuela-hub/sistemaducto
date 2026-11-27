#!/usr/bin/env python3
# **********************************************
# MARCAR FACTURAS VENCIDAS COMO PENDIENTES
# (usa .env en /srv/ducto/jobs/.env y conexión sin DSN)
# **********************************************

import os
import pyodbc
from datetime import date, timedelta
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv("/srv/ducto/jobs/.env")


def require_env(*names: str) -> None:
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        raise RuntimeError(f"Faltan variables en .env: {', '.join(missing)}")


def get_db_connection() -> pyodbc.Connection:
    require_env("SQL_SERVER", "SQL_DB", "SQL_UID", "SQL_PWD")

    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={os.getenv('SQL_SERVER')};"
        f"DATABASE={os.getenv('SQL_DB')};"
        f"UID={os.getenv('SQL_UID')};"
        f"PWD={os.getenv('SQL_PWD')};"
        "Encrypt=no;"
        "TrustServerCertificate=yes;"
        "Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)


def main() -> int:
    fec = date.today()
    fecvcto = fec + timedelta(days=30)

    # Mejor comparar por fecha directamente (sin FORMAT) para rendimiento y claridad
    # Vence si: FechaEmision + Vencimiento(días) <= hoy
    consulta = """
        UPDATE Factura
        SET Estado = 3,
            FechaPendiente = ?
        WHERE FechaPago IS NULL
          AND DATEADD(day, Vencimiento, FechaEmision) <= ?
          AND Estado = 2
    """

    try:
        with get_db_connection() as cnx:
            cur = cnx.cursor()
            cur.execute(consulta, (fecvcto, fec))
            cnx.commit()
            print("Término Normal")
            return 0
    except Exception as err:
        print(f"Error: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

