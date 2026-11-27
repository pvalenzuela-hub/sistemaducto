#!/usr/bin/env python3
# **********************************************
# CORREO SEGUIMIENTO EEPP
# **********************************************

import os
import ssl
import smtplib
import pyodbc
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from correos_omitidos import Destinatarios, MOTIVO_INVALIDA

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


def envio_correo(to_list, nombreproyecto, hes, porc, detalle):
    require_env("SMTP_USER", "SMTP_PASS")

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")

    cc = [e.strip() for e in os.getenv("MAIL_CC", "camila@ductoproyectos.cl").split(",") if e.strip()]
    to_adrs = to_list + cc

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = f"Facturación Proyecto Basura {nombreproyecto}"
    mensaje["From"] = username
    mensaje["To"] = ",".join(to_list)
    mensaje["CC"] = ",".join(cc)

    html = f"""
    <html>
    <body>
        Estimados,<br><br>
        Junto con saludar, escribo para recordar el envío de {hes} para poder facturar el {porc}% por concepto de
        "{detalle}" que se encuentra pendiente según lo cotizado.<br><br>
        Quedo atenta a su pronta respuesta.<br><br>
        Saludos cordiales,<br><br>

        <div style="text-align:left;font-size:12.8px;font-family:verdana,sans-serif">
          <b style="font-size:small;font-family:tahoma,sans-serif">Cindy Azuaje G.</b><br>
        </div><br>
        <div style="text-align:left">
          <span style="font-size:12.8px">Secretaria</span><br>
          <span style="color:rgb(34,34,34);font-size:small;font-family:tahoma,sans-serif">Ducto Proyectos y Asesorías</span>
        </div>
        <div style="text-align:left;font-family:tahoma,sans-serif;font-size:small">
          La Goleta N° 879, Las Condes
        </div>
        <a href="http://www.ductoproyectos.cl" target="_blank">www.ductoproyectos.cl</a><br>
        <img src="http://www.ductoproyectos.cl/wp-content/uploads/2017/09/logo_ductos.png">
    </body>
    </html>
    """

    mensaje.attach(MIMEText(html, "html"))
    context = ssl.create_default_context()

    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
        server.login(username, password)
        return server.sendmail(username, to_adrs, mensaje.as_string())


def main() -> int:
    consulta = "exec [ducto].[Mail_SeguimientoEEPP]"

    try:
        with get_db_connection() as cnx:
            cur = cnx.cursor()
            cur.execute(consulta)
            rows = cur.fetchall()

            if not rows:
                print("no existen registros para seguimiento")
                return 0

            filtro = Destinatarios(cnx, "seg_eepp")

            for row in rows:
                try:
                    # Según tu script:
                    # row[0]=IdFactura
                    # row[1]=to_adr
                    # row[2]=nombreproyecto
                    # row[3]=hes
                    # row[4]=porc
                    # row[5]=detalle
                    # row[6]=emailcontacto
                    id_factura = row[0]

                    destinos, omitidas = filtro.filtrar(row[1], row[6])
                    if omitidas and not filtro.queda_cliente(destinos):
                        # Solo quedan correos inválidos: no se envía. Se anota en el seguimiento la primera vez.
                        print(f"IdFactura={id_factura}: no se envía, correo inválido:", ", ".join(omitidas))
                        if filtro.registrar(omitidas, MOTIVO_INVALIDA, False, id_factura=id_factura):
                            cnx.cursor().execute(
                                "Exec [dbo].[GR_Factura_SEG] ?, ?, 0, 0, "
                                "null,null,null,null,null,null,null,null,null,'camila'",
                                (id_factura, "No se envía solicitud de EEPP/HES/Otro: correo inválido (" + ", ".join(omitidas) + ")"),
                            )
                        continue

                    rechazadas = envio_correo(destinos, row[2], row[3], row[4], row[5])
                    filtro.registrar(omitidas, MOTIVO_INVALIDA, True, id_factura=id_factura)
                    filtro.registrar_rechazadas(rechazadas, id_factura=id_factura)

                    q = cnx.cursor()
                    q.execute("UPDATE Factura SET FechaSegEEPP = GETDATE() WHERE IdFactura = ?", (id_factura,))
                    q.execute(
                        "Exec [dbo].[GR_Factura_SEG] ?, 'Se solicita EEPP/HES/Otro para Facturar', 0, 0, "
                        "null,null,null,null,null,null,null,null,null,'camila'",
                        (id_factura,),
                    )

                except Exception as e:
                    print(f"Error procesando IdFactura={row[0]}: {e}")

            cnx.commit()
            print("Término Normal")
            return 0

    except Exception as err:
        print(f"Error general: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

