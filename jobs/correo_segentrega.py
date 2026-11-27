#!/usr/bin/env python3
# **********************************************
# CORREO A CLIENTES SEGUIMIENTO ENTREGA V00
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


def envio_correo(to_list, proyecto: str, fechaprimerenvio):
    require_env("SMTP_USER", "SMTP_PASS")

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")

    # CC específico para este correo (por defecto pbarrera@...)
    cc = [e.strip() for e in os.getenv("MAIL_CC_ENTREGA_V00", "pbarrera@ductoproyectos.cl,camila@ductoproyectos.cl").split(",") if e.strip()]
    to_adrs = to_list + cc

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = f"Consulta Proyecto Basura {proyecto}"
    mensaje["From"] = username
    mensaje["To"] = ",".join(to_list)
    mensaje["CC"] = ",".join(cc)

    html = f"""
    <html>
    <body>
        Estimados,<br><br>
        Junto con saludar, escribo para consultar si ya pudieron revisar nuestra entrega de la especialidad de Basura en versión revisión de fecha {fechaprimerenvio}.
        Además, me gustaría saber si hay alguna corrección o actualización que debamos considerar para continuar con el desarrollo.
        Por otra parte, en caso que el proyecto esté terminado, pausado o detenido, les solicito que nos informen para evaluar cómo proceder con los saldos pendientes, en caso que corresponda.<br><br>
        Estamos a la espera de sus comentarios y agradecemos su pronta respuesta.<br><br>
        Saludos cordiales.<br><br>

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
    consulta = "Exec [ducto].[Mail_Seg_Entrega_V00]"

    try:
        with get_db_connection() as cnx:
            cur = cnx.cursor()
            cur.execute(consulta)
            rows = cur.fetchall()

            if not rows:
                print("No existen registros para seguimiento")
                return 0

            filtro = Destinatarios(cnx, "seg_entrega")

            for row in rows:
                try:
                    # Según tu script:
                    # row[0]=to_adr
                    # row[1]=proyecto
                    # row[2]=IdProyecto
                    # row[3]=FechaPrimerEnvio
                    to_adr = row[0]
                    proyecto = row[1]
                    id_proyecto = row[2]
                    fecha_primer_envio = row[3]

                    destinos, omitidas = filtro.filtrar(to_adr)
                    if omitidas and not filtro.queda_cliente(destinos):
                        # Solo quedan correos inválidos: no se envía ni se marca eMailSegEntregaV00, así sale cuando
                        # se corrija el contacto. Se anota en el seguimiento la primera vez.
                        print(f"IdProyecto={id_proyecto}: no se envía, correo inválido:", ", ".join(omitidas))
                        if filtro.registrar(omitidas, MOTIVO_INVALIDA, False, id_proyecto=id_proyecto):
                            cnx.cursor().execute(
                                "Exec [dbo].[GR_Proyecto_SEG] ?, ?, "
                                "null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,'camila'",
                                (id_proyecto, "No se envía consulta por revisión de la entrega V00: correo inválido (" + ", ".join(omitidas) + ")"),
                            )
                        continue

                    rechazadas = envio_correo(destinos, proyecto, fecha_primer_envio)
                    filtro.registrar(omitidas, MOTIVO_INVALIDA, True, id_proyecto=id_proyecto)
                    filtro.registrar_rechazadas(rechazadas, id_proyecto=id_proyecto)

                    q = cnx.cursor()
                    q.execute(
                        "Exec [dbo].[GR_Proyecto_SEG] ?, 'Se consulta por revisión de la entrega V00', "
                        "null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,'camila'",
                        (id_proyecto,),
                    )
                    q.execute(
                        "UPDATE Proyecto SET eMailSegEntregaV00 = GETDATE() WHERE IdProyecto = ?",
                        (id_proyecto,),
                    )

                except Exception as e:
                    print(f"Error procesando IdProyecto={row[2]}: {e}")

            cnx.commit()
            print("Término Normal")
            return 0

    except Exception as err:
        print(f"Error general: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

