from django.core.management.base import BaseCommand

from seguimiento.models import Proyecto


class Command(BaseCommand):
    help = 'Corrige CodRegion de Proyectos existentes copiandolo desde su cotizacion.'
    dry_run = False

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra los cambios sin aplicarlos.',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']

        proyectos = Proyecto.objects.select_related('idcotizacion').all()
        total = 0
        actualizados = 0
        sin_cotizacion = 0
        muestras = []

        for pro in proyectos:
            total += 1
            if not pro.idcotizacion:
                sin_cotizacion += 1
                continue

            codregion_correcto = pro.idcotizacion.codregion
            if pro.codregion == codregion_correcto:
                continue

            actualizados += 1
            if len(muestras) < 10:
                muestras.append(
                    f'  {pro.idproyecto}  CodRegion: {pro.codregion} -> {codregion_correcto}'
                )

            if not self.dry_run:
                pro.codregion = codregion_correcto
                pro.save(update_fields=['codregion'])

        if muestras:
            self.stdout.write('Muestra de cambios:')
            for m in muestras:
                self.stdout.write(m)

        if self.dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN - no se aplicaron cambios.'))
            self.stdout.write(f'Se actualizarian: {actualizados} de {total} proyectos.')
            self.stdout.write(f'Sin cotizacion: {sin_cotizacion}')
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Revisados: {total} | Actualizados: {actualizados} | '
                f'Sin cotizacion: {sin_cotizacion} | Sin cambios: {total - actualizados - sin_cotizacion}'
            ))
