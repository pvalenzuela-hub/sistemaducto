from datetime import date, timedelta
from urllib.request import urlopen
import json

from django.core.management.base import BaseCommand

from seguimiento.models import tValorUF


API_URL = 'https://mindicador.cl/api/uf'


class Command(BaseCommand):
    help = 'Sincroniza valores UF desde mindicador.cl y completa fechas faltantes.'

    def handle(self, *args, **options):
        with urlopen(API_URL, timeout=30) as response:
            payload = json.loads(response.read().decode('utf-8'))

        serie = payload.get('serie', [])
        if not serie:
            self.stdout.write(self.style.WARNING('No se recibieron datos UF desde la API.'))
            return

        existentes = set(tValorUF.objects.values_list('Fecha', flat=True))
        creados = 0

        for item in serie:
            fecha = item.get('fecha', '')[:10]
            valor = item.get('valor')
            if not fecha or valor is None:
                continue

            fecha_obj = date.fromisoformat(fecha)
            if fecha_obj in existentes:
                continue

            tValorUF.objects.create(Fecha=fecha_obj, ValorUF=valor)
            creados += 1

        self.stdout.write(self.style.SUCCESS(f'Sincronización UF completada. Nuevos registros: {creados}'))
