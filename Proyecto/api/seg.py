"""Acceso a Factura_Seg (comentarios de seguimiento). PK compuesta (IdFactura, IdReg), sin modelo ORM."""
from django.db import connection
from django.utils import timezone


def _row_to_dict(row):
    idreg, fecha, comentario, usuario = row
    return {'idreg': idreg, 'fecha': fecha, 'usuario': usuario, 'comentario': comentario}


def listar(idfactura):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT IdReg, FechaRevision, Comentario, IdUsuario FROM Factura_Seg '
            'WHERE IdFactura = %s ORDER BY IdReg DESC', [idfactura])
        return [_row_to_dict(r) for r in cursor.fetchall()]


def obtener(idfactura, idreg):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT IdReg, FechaRevision, Comentario, IdUsuario FROM Factura_Seg '
            'WHERE IdFactura = %s AND IdReg = %s', [idfactura, idreg])
        row = cursor.fetchone()
    return _row_to_dict(row) if row else None


def ultimos(idfacturas):
    """{idfactura: texto del último comentario} para varias facturas en una sola consulta."""
    if not idfacturas:
        return {}
    placeholders = ', '.join(['%s'] * len(idfacturas))
    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT s.IdFactura, s.Comentario FROM Factura_Seg s '
            f'JOIN (SELECT IdFactura, MAX(IdReg) AS IdReg FROM Factura_Seg '
            f'      WHERE IdFactura IN ({placeholders}) GROUP BY IdFactura) m '
            f'ON s.IdFactura = m.IdFactura AND s.IdReg = m.IdReg', list(idfacturas))
        return dict(cursor.fetchall())


def agregar(idfactura, comentario, usuario):
    """Inserta un comentario con IdReg = MAX + 1. Debe llamarse dentro de transaction.atomic()."""
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT COALESCE(MAX(IdReg), 0) + 1 FROM Factura_Seg WITH (UPDLOCK, HOLDLOCK) WHERE IdFactura = %s'
            if connection.vendor == 'microsoft' else
            'SELECT COALESCE(MAX(IdReg), 0) + 1 FROM Factura_Seg WHERE IdFactura = %s', [idfactura])
        idreg = cursor.fetchone()[0]
        cursor.execute(
            'INSERT INTO Factura_Seg (IdFactura, IdReg, FechaRevision, Comentario, EsRecordatorio, IdUsuario, Estado) '
            'VALUES (%s, %s, %s, %s, 0, %s, 0)',
            [idfactura, idreg, timezone.localtime().replace(tzinfo=None), comentario, usuario])
    return obtener(idfactura, idreg)


def editar(idfactura, idreg, comentario):
    with connection.cursor() as cursor:
        cursor.execute(
            'UPDATE Factura_Seg SET Comentario = %s, FechaRevision = %s WHERE IdFactura = %s AND IdReg = %s',
            [comentario, timezone.localtime().replace(tzinfo=None), idfactura, idreg])
    return obtener(idfactura, idreg)
