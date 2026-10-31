import hashlib
import secrets

from django.db import models


def hash_key(raw_key):
    return hashlib.sha256(raw_key.encode()).hexdigest()


class ApiKey(models.Model):
    """API Key de un sistema externo. Solo se guarda el hash; la clave se muestra una vez al crearla."""
    nombre = models.CharField(max_length=100, unique=True)
    prefijo = models.CharField(max_length=8)
    key_hash = models.CharField(max_length=64, unique=True)
    activa = models.BooleanField(default=True)
    creada = models.DateTimeField(auto_now_add=True)
    ultimo_uso = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'api_apikey'

    def __str__(self):
        return f"{self.nombre} ({self.prefijo}...)"

    @classmethod
    def generar(cls, nombre):
        raw_key = secrets.token_urlsafe(32)
        obj = cls.objects.create(nombre=nombre, prefijo=raw_key[:8], key_hash=hash_key(raw_key))
        return obj, raw_key
