#!/usr/bin/env python3
# **********************************************
# PENDIENTE PAGO - MARCA FACTURAS Y REGISTRA SEG POR PROYECTO
# **********************************************

import os
import pyodbc
from dotenv import load_dotenv

# Cargar variables de entorno desde /srv/ducto/jobs/.env
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
    consulta = "exec [ducto].[Robot_FacturaPendientePago]"
    mensaje_seg = (
        "ATENTOS!!! Hay facturas atrasadas por este proyecto. "
        "No hacer entregas sin consultar a Cindy o Camila."
    )

    try:
        with get_db_connection() as cnx:
            cur = cnx.cursor()
            cur.execute(consulta)
            rows = cur.fetchall()

            if not rows:
                print("no existen registros")
                return 0

            # Para no duplicar GR_Proyecto_SEG por proyecto.
            # Tu versión asumía que viene ordenado; esto funciona incluso si no lo viene.
            proyectos_procesados = set()

            for row in rows:
                # Se asume:
                # row[0] = IdProyecto
                # row[1] = IdFactura
                id_proyecto = row[0]
                id_factura = row[1]

                try:
                    q = cnx.cursor()

                    if id_proyecto not in proyectos_procesados:
                        # El SP original recibe muchos parámetros; aquí solo parametrizamos el IdProyecto
                        # y dejamos el texto fijo igual que tu script (con 'camila' al final).
                        q.execute(
                            "Exec [dbo].[GR_Proyecto_SEG] ?, ?, "
                            "null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,'camila'",
                            (id_proyecto, mensaje_seg),
                        )
                        proyectos_procesados.add(id_proyecto)

                    # Marcar factura como procesada por robot
                    q.execute(
                        "UPDATE Factura SET RobotPendientePago = 1 WHERE IdFactura = ?",
                        (id_factura,),
                    )

                except Exception as err:
                    print(f"Error procesando IdProyecto={id_proyecto} IdFactura={id_factura}: {err}")

            cnx.commit()
            print("termino proceso normal")
            return 0

    except Exception as err:
        print(f"Error general: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

