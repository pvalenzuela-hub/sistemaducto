import hashlib
import json
import secrets

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


def hash_key(raw_key):
    return hashlib.sha256(raw_key.encode()).hexdigest()


class ApiKey(models.Model):
    """API Key de un sistema externo. Solo se guarda el hash; la clave se muestra una vez al crearla.

    Toda clave activa puede leer. Los permisos 'comentar' y 'editar' se habilitan por separado.
    """
    nombre = models.CharField(max_length=100, unique=True)
    prefijo = models.CharField(max_length=8)
    key_hash = models.CharField(max_length=64, unique=True)
    activa = models.BooleanField(default=True)
    comentar = models.BooleanField(default=False, help_text='Permite agregar y editar comentarios de bitácora')
    editar = models.BooleanField(default=False, help_text='Permite cambiar estado de facturas y proyectos')
    creada = models.DateTimeField(auto_now_add=True)
    ultimo_uso = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'api_apikey'

    def __str__(self):
        return f"{self.nombre} ({self.prefijo}...)"

    @property
    def usuario_seg(self):
        """Autor de los comentarios en Factura_Seg / Proyecto_Seg (IdUsuario, varchar 15)."""
        return f"api:{self.nombre}"[:15]

    @property
    def permisos_texto(self):
        return ', '.join(['lectura'] + [p for p in ('comentar', 'editar') if getattr(self, p)])

    @classmethod
    def generar(cls, nombre, comentar=False, editar=False):
        raw_key = secrets.token_urlsafe(32)
        obj = cls.objects.create(nombre=nombre, prefijo=raw_key[:8], key_hash=hash_key(raw_key),
                                 comentar=comentar, editar=editar)
        return obj, raw_key


class ApiCambio(models.Model):
    """Registro de cada cambio hecho a través de la API, con los valores antes y después, para revisar o revertir."""
    ACCIONES = [
        ('editar', 'Editar'),
        ('comentar', 'Agregar comentario'),
        ('editar_comentario', 'Editar comentario'),
        ('revertir', 'Revertir'),
    ]

    fecha = models.DateTimeField(auto_now_add=True)
    api_key = models.ForeignKey(ApiKey, on_delete=models.PROTECT, null=True, blank=True)
    usuario = models.CharField(max_length=100, help_text='Clave de API o usuario del sistema que hizo el cambio')
    metodo = models.CharField(max_length=10, blank=True)
    ruta = models.CharField(max_length=255, blank=True)
    entidad = models.CharField(max_length=30)
    entidad_id = models.CharField(max_length=30)
    accion = models.CharField(max_length=20, choices=ACCIONES)
    antes = models.TextField(blank=True, default='')
    despues = models.TextField(blank=True, default='')
    revertido_por = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='revierte')

    class Meta:
        db_table = 'api_cambio'
        ordering = ['-id']
        indexes = [models.Index(fields=['entidad', 'entidad_id'], name='api_cambio_entidad_idx')]

    def __str__(self):
        return f"#{self.pk} {self.fecha:%Y-%m-%d %H:%M} {self.usuario} {self.accion} {self.entidad} {self.entidad_id}"

    @staticmethod
    def _dump(value):
        return '' if value is None else json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False)

    @staticmethod
    def _load(value):
        return json.loads(value) if value else None

    @property
    def antes_data(self):
        return self._load(self.antes)

    @property
    def despues_data(self):
        return self._load(self.despues)

    @classmethod
    def registrar(cls, request, entidad, entidad_id, accion, antes=None, despues=None):
        api_key = getattr(request, 'api_key', None) if request is not None else None
        return cls.objects.create(
            api_key=api_key,
            usuario=api_key.nombre if api_key else 'sistema',
            metodo=request.method if request is not None else '',
            ruta=request.path[:255] if request is not None else '',
            entidad=entidad,
            entidad_id=str(entidad_id),
            accion=accion,
            antes=cls._dump(antes),
            despues=cls._dump(despues),
        )
