"""Destinatarios de los avisos por correo del cron (cobranza 1 y 2, aviso de pago, EEPP y entrega V00).

- No se escribe a las direcciones marcadas como inválidas por rebote (dbo.CorreoRebotado, Estado = 'invalida').
- Cada dirección omitida, y cada dirección que el servidor de correo rechaza al enviar, queda en dbo.CorreoOmitido
  (ver Proyecto/sql/2026-11-27_CorreoOmitido.sql). La web las muestra en Clientes > Correos por corregir.
- Si después de omitir no queda ninguna dirección del cliente, el aviso no se envía y no se marca como enviado:
  sale solo cuando se corrige el correo del contacto.

Si la consulta de las marcas o el registro fallan, los avisos siguen saliendo como antes.
"""
import re

DOMINIO_INTERNO = "@ductoproyectos.cl"
MOTIVO_INVALIDA = "invalida"    # marcada por rebote: no se le escribió
MOTIVO_RECHAZADA = "rechazada"  # el servidor de correo la rechazó al enviar


def separar(texto):
    """Direcciones de un campo de correo, que puede traer varias separadas por ; , / o espacios."""
    if texto in (0, None):
        return []
    partes = (p.strip().strip("<>").rstrip(".") for p in re.split(r"[;,/\s]+", str(texto).strip()))
    return [p for p in partes if p]


class Destinatarios:
    def __init__(self, cnx, proceso):
        self.cnx = cnx
        self.proceso = proceso
        try:
            filas = cnx.cursor().execute("SELECT Email FROM dbo.CorreoRebotado WHERE Estado = 'invalida'").fetchall()
            self.invalidas = {f[0].strip().lower() for f in filas if f[0]}
        except Exception as e:
            print(f"No se pudieron leer los correos inválidos (se envía a todos): {e}")
            self.invalidas = set()

    def filtrar(self, *campos):
        """(direcciones a las que se escribe, direcciones omitidas por inválidas), sin repetir."""
        destinos, omitidas = [], []
        for campo in campos:
            for correo in separar(campo):
                lista = omitidas if correo.lower() in self.invalidas else destinos
                if correo.lower() not in (c.lower() for c in lista):
                    lista.append(correo)
        return destinos, omitidas

    @staticmethod
    def queda_cliente(destinos):
        """¿Queda alguna dirección que no sea interna de Ducto?"""
        return any(not d.lower().endswith(DOMINIO_INTERNO) for d in destinos)

    def registrar(self, correos, motivo, enviado, id_factura=None, id_proyecto=None, detalle=None):
        """Deja cada dirección en dbo.CorreoOmitido. Si ya estaba por el mismo aviso, suma una vez más.
        Devuelve True si alguna es nueva (para anotar el seguimiento solo la primera vez)."""
        nueva = False
        for correo in correos:
            try:
                cur = self.cnx.cursor()
                cur.execute(
                    "UPDATE dbo.CorreoOmitido SET Veces = Veces + 1, UltimaFecha = dbo.Hora_Local(), Enviado = ?, "
                    "Detalle = ? WHERE Proceso = ? AND Email = ? AND Motivo = ? "
                    "AND ISNULL(IdFactura, 0) = ? AND ISNULL(IdProyecto, 0) = ?",
                    (1 if enviado else 0, detalle, self.proceso, correo.lower(), motivo,
                     int(id_factura or 0), int(id_proyecto or 0)),
                )
                if cur.rowcount == 0:
                    cur.execute(
                        "INSERT INTO dbo.CorreoOmitido (Proceso, Email, Motivo, Detalle, IdFactura, IdProyecto, "
                        "Enviado, Fecha, UltimaFecha, Veces) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, dbo.Hora_Local(), dbo.Hora_Local(), 1)",
                        (self.proceso, correo.lower(), motivo, detalle,
                         int(id_factura) if id_factura else None, int(id_proyecto) if id_proyecto else None,
                         1 if enviado else 0),
                    )
                    nueva = True
            except Exception as e:
                print(f"No se pudo registrar el correo omitido {correo}: {e}")
        return nueva

    def registrar_rechazadas(self, rechazadas, id_factura=None, id_proyecto=None):
        """rechazadas: lo que devuelve smtplib.sendmail, {dirección: (código, mensaje)}. Las internas no se anotan."""
        for correo, respuesta in (rechazadas or {}).items():
            if correo.lower().endswith(DOMINIO_INTERNO):
                continue
            codigo, mensaje = (tuple(respuesta) + ("", ""))[:2] if isinstance(respuesta, (tuple, list)) else ("", respuesta)
            if isinstance(mensaje, bytes):
                mensaje = mensaje.decode("utf-8", "replace")
            print(f"Rechazada por el servidor de correo: {correo} ({codigo})")
            self.registrar([correo], MOTIVO_RECHAZADA, True, id_factura, id_proyecto, f"{codigo} {mensaje}".strip()[:500])
