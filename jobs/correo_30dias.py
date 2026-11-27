#!/usr/bin/env python3
# **********************************************
# COBRANZA 1 - ENVÍA CORREO (Mar-Vie) y marca Factura
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


def envio_correo(to_list, factura, femision, monto, facturado, detalle, proyecto, dias, frase1, frase2):
    require_env("SMTP_USER", "SMTP_PASS")

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")

    cc = [e.strip() for e in os.getenv("MAIL_CC", "camila@ductoproyectos.cl").split(",") if e.strip()]
    to_adrs = to_list + cc

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = f"Informa Factura pendiente de pago N° {factura}"
    mensaje["From"] = username
    mensaje["To"] = ",".join(to_list)
    mensaje["CC"] = ",".join(cc)

    html = f"""
    <html>
    <body>
        Estimados,<br><br>
        Junto con saludar, escribo para consultar por fecha de pago de la factura que se detalla a continuación:<br><br>
        Factura N°: {factura}<br>
        Fecha Emisión: {femision}<br>
        Monto: {monto}<br>
        % Facturado: {facturado}%<br>
        Detalle: {detalle}<br>
        Nombre Proyecto: {proyecto}<br>
        {frase1}<br>
        {frase2}<br><br>
        Lo anterior dado que ya han transcurridos {dias} días desde su emisión.<br><br>
        Quedamos atentos.<br><br>

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
    # Martes(1) a Viernes(4)
    dia_semana = datetime.now().weekday()
    if not (1 <= dia_semana <= 4):
        print("hoy no es entre Martes y Viernes")
        return 0

    consulta = "exec [ducto].[Mail_RescataCobranza_1]"

    try:
        with get_db_connection() as cnx:
            cur = cnx.cursor()
            cur.execute(consulta)
            rows = cur.fetchall()

            if not rows:
                print("sin registros")
                return 0

            # Tu lógica original intentaba detectar un 'flag' con r[0]==0.
            # Aquí lo hacemos robusto: si algún row trae to_adr vacío/0, se ignora ese row,
            # y seguimos con los que sí tienen destinatario.
            rows_validas = [r for r in rows if r[0] not in (0, None, "")]

            if not rows_validas:
                print("sin destinatarios válidos (seguir=0)")
                return 0

            filtro = Destinatarios(cnx, "cobranza_1")

            for row in rows_validas:
                try:
                    # Según tu script:
                    # row[0]=to, row[1]=factura, row[2]=femision, row[3]=monto, row[4]=facturado,
                    # row[5]=detalle, row[6]=proyecto, row[7]=IdFactura,
                    # row[8]=dias, row[9]=frase1, row[10]=frase2, row[11]=copia
                    destinos, omitidas = filtro.filtrar(row[0], row[11])
                    if omitidas and not filtro.queda_cliente(destinos):
                        # Solo quedan correos inválidos: no se envía ni se marca Correo_1, así sale cuando se
                        # corrija el contacto. Se anota en el seguimiento la primera vez.
                        print(f"Factura {row[1]}: no se envía, correo inválido:", ", ".join(omitidas))
                        if filtro.registrar(omitidas, MOTIVO_INVALIDA, False, id_factura=row[7]):
                            cnx.cursor().execute(
                                "Exec [dbo].[GR_Factura_SEG] ?, ?, 0, 0, "
                                "null,null,null,null,null,null,null,null,null,'camila'",
                                (row[7], "No se envía correo de cobranza 1: correo inválido (" + ", ".join(omitidas) + ")"),
                            )
                        continue

                    rechazadas = envio_correo(destinos, row[1], row[2], row[3], row[4], row[5], row[6], row[8], row[9], row[10])
                    filtro.registrar(omitidas, MOTIVO_INVALIDA, True, id_factura=row[7])
                    filtro.registrar_rechazadas(rechazadas, id_factura=row[7])

                    q = cnx.cursor()
                    q.execute("UPDATE Factura SET Correo_1 = 1 WHERE IdFactura = ?", (row[7],))
                    q.execute(
                        "Exec [dbo].[GR_Factura_SEG] ?, 'Se envia correo de cobranza 1', 0, 0, "
                        "null,null,null,null,null,null,null,null,null,'camila'",
                        (row[7],),
                    )

                except Exception as e:
                    print(f"Error procesando IdFactura={row[7]} Factura={row[1]}: {e}")

            cnx.commit()
            print("termino normal")
            return 0

    except Exception as err:
        print(f"Error general: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

