"""Bitácoras de seguimiento Factura_Seg y Proyecto_Seg. PK compuesta (IdFactura|IdProyecto, IdReg), sin modelo ORM.

Las fechas se guardan en hora local de Chile sin zona horaria, igual que la aplicación web.
"""
from django.db import connection
from django.utils import timezone


class Bitacora:
    def __init__(self, tabla, col_id, col_fecha, con_estado):
        self.tabla = tabla
        self.col_id = col_id
        self.col_fecha = col_fecha
        self.con_estado = con_estado  # Proyecto_Seg guarda el estado del proyecto al momento del comentario

    @property
    def _select(self):
        extra = ', Estado' if self.con_estado else ''
        return f'SELECT IdReg, {self.col_fecha}, Comentario, IdUsuario{extra} FROM {self.tabla}'

    def _row_to_dict(self, row):
        data = {'idreg': row[0], 'fecha': row[1], 'usuario': row[3], 'comentario': row[2]}
        if self.con_estado:
            data['estado'] = row[4]
        return data

    def listar(self, id_):
        with connection.cursor() as cursor:
            cursor.execute(f'{self._select} WHERE {self.col_id} = %s ORDER BY IdReg DESC', [id_])
            return [self._row_to_dict(r) for r in cursor.fetchall()]

    def obtener(self, id_, idreg):
        with connection.cursor() as cursor:
            cursor.execute(f'{self._select} WHERE {self.col_id} = %s AND IdReg = %s', [id_, idreg])
            row = cursor.fetchone()
        return self._row_to_dict(row) if row else None

    def ultimos(self, ids):
        """{id: texto del último comentario} para varios registros en una sola consulta."""
        ids = list(ids)
        if not ids:
            return {}
        placeholders = ', '.join(['%s'] * len(ids))
        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT s.{self.col_id}, s.Comentario FROM {self.tabla} s '
                f'JOIN (SELECT {self.col_id}, MAX(IdReg) AS IdReg FROM {self.tabla} '
                f'      WHERE {self.col_id} IN ({placeholders}) GROUP BY {self.col_id}) m '
                f'ON s.{self.col_id} = m.{self.col_id} AND s.IdReg = m.IdReg', ids)
            return {int(k): v for k, v in cursor.fetchall()}

    def agregar(self, id_, comentario, usuario, estado=0):
        """Inserta un comentario con IdReg = MAX + 1. Debe llamarse dentro de transaction.atomic()."""
        lock = ' WITH (UPDLOCK, HOLDLOCK)' if connection.vendor == 'microsoft' else ''
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT COALESCE(MAX(IdReg), 0) + 1 FROM {self.tabla}{lock} WHERE {self.col_id} = %s', [id_])
            idreg = cursor.fetchone()[0]
            ahora = timezone.localtime().replace(tzinfo=None)
            if self.con_estado:
                cursor.execute(
                    f'INSERT INTO {self.tabla} ({self.col_id}, IdReg, {self.col_fecha}, Comentario, EsRecordatorio, '
                    f'IdUsuario, Estado) VALUES (%s, %s, %s, %s, 0, %s, %s)',
                    [id_, idreg, ahora, comentario, usuario, estado or 0])
            else:
                cursor.execute(
                    f'INSERT INTO {self.tabla} ({self.col_id}, IdReg, {self.col_fecha}, Comentario, EsRecordatorio, '
                    f'IdUsuario, Estado) VALUES (%s, %s, %s, %s, 0, %s, 0)',
                    [id_, idreg, ahora, comentario, usuario])
        return self.obtener(id_, idreg)

    def editar(self, id_, idreg, comentario):
        with connection.cursor() as cursor:
            cursor.execute(
                f'UPDATE {self.tabla} SET Comentario = %s, {self.col_fecha} = %s WHERE {self.col_id} = %s AND IdReg = %s',
                [comentario, timezone.localtime().replace(tzinfo=None), id_, idreg])
        return self.obtener(id_, idreg)

    def eliminar(self, id_, idreg):
        with connection.cursor() as cursor:
            cursor.execute(f'DELETE FROM {self.tabla} WHERE {self.col_id} = %s AND IdReg = %s', [id_, idreg])


factura = Bitacora('Factura_Seg', 'IdFactura', 'FechaRevision', con_estado=False)
proyecto = Bitacora('Proyecto_Seg', 'IdProyecto', 'Fecha', con_estado=True)
