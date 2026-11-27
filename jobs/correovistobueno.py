#!/usr/bin/env python3
# **********************************************
# CORREO VISTO BUENO - INGRESO SEREMI
# **********************************************

import os
import ssl
import smtplib
import pyodbc
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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


def envio_correo(to_adr: str, proyecto: str) -> None:
    require_env("SMTP_USER", "SMTP_PASS")

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")

    # CC específico para este correo (por defecto pbarrera@...)
    cc = [e.strip() for e in os.getenv("MAIL_CC_VISTOBUENO", "pbarrera@ductoproyectos.cl").split(",") if e.strip()]
    to_list = [x for x in [to_adr] if x]
    to_adrs = to_list + cc

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = f"Ingreso Seremi Proyecto Basura - {proyecto}"
    mensaje["From"] = username
    mensaje["To"] = ",".join(to_list)
    mensaje["CC"] = ",".join(cc)

    html = f"""
    <html>
    <body>
        Estimados,<br><br>
        Junto con saludar, escribo para consultar si han tenido la oportunidad de revisar nuestra última entrega de la
        Especialidad de Residuos y si existen correcciones o actualizaciones que debamos considerar antes de continuar
        con el desarrollo, o si dicha entrega cuenta con su visto bueno para el ingreso a SEREMI.<br><br>

        Además, queremos informarles que el proceso de revisión y emisión de observaciones por parte del SEREMI
        generalmente lleva alrededor de 2 meses. Por lo tanto, les recomendamos que nos informen con suficiente
        anticipación cuando el proyecto cuente con visto bueno para ingreso a SEREMI. Si esperamos hasta el último
        momento, podrían enfrentar retrasos en la etapa de ejecución de las obras.<br><br>

        Quedamos atentos a sus comentarios y les agradecemos de antemano su pronta respuesta.<br><br>
        Saludos cordiales.<br><br>

        <div style="text-align:left;font-size:12.8px;font-family:verdana,sans-serif">
          <b style="font-size:small;font-family:tahoma,sans-serif">Camila Valenzuela Dueñas</b><br>
        </div><br>
        <div style="text-align:left">
          <span style="font-size:12.8px">Gerente Area Comercial</span><br>
          <span style="color:rgb(34,34,34);font-size:small;font-family:tahoma,sans-serif">Ducto Proyectos y Asesorías</span>
        </div>
        <div style="text-align:left;font-family:tahoma,sans-serif;font-size:small">
          La Goleta N° 879, Las Condes<br>9 6 2465645 / 22 261 5416
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
        server.sendmail(username, to_adrs, mensaje.as_string())


def main() -> int:
    consulta = "EXEC [ducto].[Mail_VistoBueno]"

    try:
        with get_db_connection() as cnx:
            cur = cnx.cursor()
            cur.execute(consulta)
            rows = cur.fetchall()

            if not rows:
                print("no existen registros para seguimiento")
                return 0

            for row in rows:
                try:
                    # Según tu script:
                    # row[0]=to_adr
                    # row[1]=proyecto
                    # row[2]=IdProyecto
                    to_adr = row[0]
                    proyecto = row[1]
                    id_proyecto = row[2]

                    envio_correo(to_adr, proyecto)

                    q = cnx.cursor()
                    q.execute(
                        "UPDATE Proyecto SET eMailEnvioVistoBueno = GETDATE() WHERE IdProyecto = ?",
                        (id_proyecto,),
                    )
                    q.execute(
                        "Exec [dbo].[GR_Proyecto_SEG] ?, 'Se envia correo, solicitando Visto Bueno para Ingreso a SEREMI', "
                        "null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,'camila'",
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

