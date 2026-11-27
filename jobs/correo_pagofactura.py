#!/usr/bin/env python3
# **********************************************
# CORREO A CLIENTES POR PAGO DE FACTURA
# **********************************************

import os
import ssl
import smtplib
import pyodbc
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from correos_omitidos import Destinatarios, MOTIVO_INVALIDA


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


def send_email(to_list, factura, fechapago, nombreproyecto: str):
    require_env("SMTP_USER", "SMTP_PASS")

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")

    cc = [e.strip() for e in os.getenv("MAIL_CC", "camila@ductoproyectos.cl").split(",") if e.strip()]
    to_adrs = to_list + cc

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Notificación Pago Recibido Factura {factura}"
    msg["From"] = username
    msg["To"] = ",".join(to_list)
    msg["CC"] = ",".join(cc)

    html = f"""
    <html>
    <body>
        Estimados,<br><br>
        Junto con saludar, se confirma recepción del pago de fecha {fechapago}
        correspondiente a la factura N° {factura} por el proyecto de residuos {nombreproyecto}.<br><br>
        Saludos cordiales.<br><br>
        PD: Este es un correo automático, en caso que ya hayamos acusado recibo del pago, favor no considerar.<br><br>
        Atte.<br><br>

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

    msg.attach(MIMEText(html, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
        server.login(username, password)
        return server.sendmail(username, to_adrs, msg.as_string())


def main() -> int:
    consulta = "Exec [ducto].[Mail_AvisoPago]"

    try:
        with get_db_connection() as cnx:
            cursor = cnx.cursor()
            cursor.execute(consulta)
            rows = cursor.fetchall()

            if not rows:
                print("no existen registros para procesar...")
                return 0

            filtro = Destinatarios(cnx, "aviso_pago")

            for row in rows:
                # Esperado por tu SP:
                # row[0]=to, row[1]=email cobro, row[2]=IdFactura, row[3]=factura, row[4]=fechapago, row[5]=nombreproyecto
                id_factura = row[2]
                try:
                    destinos, omitidas = filtro.filtrar(row[0], row[1])
                    if omitidas and not filtro.queda_cliente(destinos):
                        # Solo quedan correos inválidos: no se envía ni se marca CorreoAvisoPago, así sale cuando
                        # se corrija el contacto. Se anota en el seguimiento la primera vez.
                        print(f"IdFactura={id_factura}: no se envía, correo inválido:", ", ".join(omitidas))
                        if filtro.registrar(omitidas, MOTIVO_INVALIDA, False, id_factura=id_factura):
                            cnx.cursor().execute(
                                "Exec [dbo].[GR_Factura_SEG] ?, ?, 0, 0, "
                                "null,null,null,null,null,null,null,null,null,'camila'",
                                (id_factura, "No se envía aviso de pago recibido: correo inválido (" + ", ".join(omitidas) + ")"),
                            )
                        continue

                    rechazadas = send_email(destinos, row[3], row[4], row[5])
                    filtro.registrar(omitidas, MOTIVO_INVALIDA, True, id_factura=id_factura)
                    filtro.registrar_rechazadas(rechazadas, id_factura=id_factura)

                    # Parametrizado
                    cnx.cursor().execute(
                        "UPDATE Factura SET CorreoAvisoPago=1, FechaAvisoPago=GETDATE() WHERE IdFactura=?",
                        id_factura,
                    )

                    cnx.cursor().execute(
                        "Exec [dbo].[GR_Factura_SEG] ?, 'Se confirma recepción de pago de factura', 0, 0, "
                        "null,null,null,null,null,null,null,null,null,'camila'",
                        id_factura,
                    )

                except Exception as e:
                    print(f"Error procesando IdFactura={id_factura}: {e}")

            cnx.commit()
            print("termino normal")
            return 0

    except Exception as err:
        print(f"Error general: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

