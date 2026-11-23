from django.core.management.base import BaseCommand

from seguimiento.servicios import uf


class Command(BaseCommand):
    help = 'Agrega a tValorUF las fechas de UF que falten (mindicador.cl; si no responde, findic.cl o SII).'

    def handle(self, *args, **options):
        nuevos, fuente = uf.sincronizar_faltantes()
        if fuente is None:
            self.stdout.write(self.style.WARNING('Ninguna fuente de UF respondió (mindicador.cl, findic.cl, SII).'))
            return
        self.stdout.write(self.style.SUCCESS(f'Sincronización UF completada desde {fuente}. Nuevos registros: {nuevos}'))
