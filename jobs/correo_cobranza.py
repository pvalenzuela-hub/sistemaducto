#!/usr/bin/env python3
# **********************************************
# COBRANZA 2 - ENVÍA CORREO (Programar Lunes 18:00 America/Santiago)
# **********************************************

import os
import ssl
import smtplib
import pyodbc
from dotenv import load_dotenv
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from correos_omitidos import Destinatarios, MOTIVO_INVALIDA

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


def envio_correo(to_list, factura, femision, monto, facturado, detalle, proyecto, frase1, frase2):
    require_env("SMTP_USER", "SMTP_PASS")

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")

    cc = [e.strip() for e in os.getenv("MAIL_CC", "camila@ductoproyectos.cl").split(",") if e.strip()]
    to_adrs = to_list + cc

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = f"Factura N° {factura} pendiente de pago - Ducto Proyectos"
    mensaje["From"] = username
    mensaje["To"] = ",".join(to_list)
    mensaje["CC"] = ",".join(cc)

    html = f"""
    <html>
    <body>
        Estimados,<br><br>
        Junto con saludar, rogamos informar fecha de pago de la factura en mención, la cual se encuentra atrasada.<br>
        Se indica detalle a continuación:<br><br>
        Factura N°: {factura}<br>
        Fecha Emisión: {femision}<br>
        Monto: {monto}<br>
        % Facturado: {facturado}%<br>
        Detalle: {detalle}<br>
        Nombre Proyecto: {proyecto}<br>
        {frase1}<br>
        {frase2}<br><br>
        De antemano muchas gracias.<br>
        Saludos.<br><br>

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
    # Si lo programas por cron solo lunes, no necesitas validar el día.
    # Igual lo dejo como “cinturón y tirantes” por si alguien lo ejecuta manual otro día.
    if datetime.now().weekday() != 0:
        print("Hoy no es lunes, no se ejecuta (ejecución manual).")
        return 0

    consulta = "exec [ducto].[Mail_RescataCobranza_2]"

    try:
        with get_db_connection() as cnx:
            cur = cnx.cursor()
            cur.execute(consulta)
            rows = cur.fetchall()

            if not rows:
                print("sin registros para cobranza 2")
                return 0

            filtro = Destinatarios(cnx, "cobranza_2")

            for row in rows:
                try:
                    # Según tu script:
                    # row[0]=to, row[1]=factura, row[2]=femision, row[3]=monto, row[4]=facturado,
                    # row[5]=detalle, row[6]=proyecto, row[7]=IdFactura (para SEG),
                    # row[8]=frase1, row[9]=frase2, row[10]=copia
                    print("Factura -->", row[1])
                    destinos, omitidas = filtro.filtrar(row[0], row[10])
                    if omitidas and not filtro.queda_cliente(destinos):
                        # Solo quedan correos inválidos: no se envía. Se anota en el seguimiento la primera vez.
                        print("  no se envía, correo inválido:", ", ".join(omitidas))
                        if filtro.registrar(omitidas, MOTIVO_INVALIDA, False, id_factura=row[7]):
                            cnx.cursor().execute(
                                "Exec [dbo].[GR_Factura_SEG] ?, ?, 0, 0, "
                                "null,null,null,null,null,null,null,null,null,'camila'",
                                (row[7], "No se envía correo de cobranza 2: correo inválido (" + ", ".join(omitidas) + ")"),
                            )
                        continue

                    rechazadas = envio_correo(destinos, row[1], row[2], row[3], row[4], row[5], row[6], row[8], row[9])
                    filtro.registrar(omitidas, MOTIVO_INVALIDA, True, id_factura=row[7])
                    filtro.registrar_rechazadas(rechazadas, id_factura=row[7])

                    # Parametrizado (IdFactura)
                    cnx.cursor().execute(
                        "Exec [dbo].[GR_Factura_SEG] ?, 'Se envia correo de cobranza 2', 0, 0, "
                        "null,null,null,null,null,null,null,null,null,'camila'",
                        (row[7],),
                    )
                except Exception as e:
                    print(f"Error enviando/registrando factura {row[1]} (IdFactura={row[7]}): {e}")

            cnx.commit()
            print("termino normal")
            return 0

    except Exception as err:
        print(f"Error general: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

