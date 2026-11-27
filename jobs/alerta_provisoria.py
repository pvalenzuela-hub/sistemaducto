#!/usr/bin/env python3
# **********************************************
# ALERTA PROVISORIA - MARCA FACTURAS Y REGISTRA SEG POR PROYECTO
# **********************************************

import os
import pyodbc
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
    consulta = "EXEC [ducto].[Robot_AlertaProvisoria]"
    mensaje_seg = (
        "ATENTOS!!! Hay HES o EEPP Pendiente por Enviar. "
        "No hacer entregas sin consultar a Cindy o Camila."
    )

    try:
        with get_db_connection() as cnx:
            cur = cnx.cursor()
            cur.execute(consulta)
            rows = cur.fetchall()

            # Si quieres debug:
            # print(f"filas: {len(rows)}")

            if not rows:
                return 0

            # Para no duplicar GR_Proyecto_SEG por proyecto,
            # no dependemos del orden de la query.
            proyectos_procesados = set()

            for row in rows:
                # ⚠️ IMPORTANTE:
                # En tu script original usabas:
                # - UPDATE Factura ... Where IdFactura = row[0]
                # - GR_Proyecto_SEG ... {row[1]}
                # Así que interpretamos:
                # row[0] = IdFactura
                # row[1] = IdProyecto
                id_factura = row[0]
                id_proyecto = row[1]

                try:
                    q = cnx.cursor()

                    if id_proyecto not in proyectos_procesados:
                        q.execute(
                            "EXEC [dbo].[GR_Proyecto_SEG] ?, ?, "
                            "null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,'camila'",
                            (id_proyecto, mensaje_seg),
                        )
                        proyectos_procesados.add(id_proyecto)

                    q.execute(
                        "UPDATE Factura SET Alerta_Provisoria = 1 WHERE IdFactura = ?",
                        (id_factura,),
                    )

                except Exception as err:
                    print(f"Error procesando IdProyecto={id_proyecto} IdFactura={id_factura}: {err}")

            cnx.commit()
            return 0

    except Exception as err:
        print(f"Error general: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

