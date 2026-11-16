from django.core.management.base import BaseCommand, CommandError
from django.utils.timezone import localtime

from api.models import ApiCambio
from api.reversion import NoReversible, describir, revertir


class Command(BaseCommand):
    help = "Revisa y revierte los cambios hechos a través de la API."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='accion', required=True)
        listar = sub.add_parser('listar', help='Lista los últimos cambios')
        listar.add_argument('--clave', help='Nombre de la API Key')
        listar.add_argument('--entidad', help='factura, factura_comentario, proyecto, proyecto_comentario')
        listar.add_argument('--id', help='Id de la factura o proyecto')
        listar.add_argument('--limite', type=int, default=50)
        ver = sub.add_parser('ver', help='Muestra el detalle de un cambio')
        ver.add_argument('cambio', type=int)
        rev = sub.add_parser('revertir', help='Revierte un cambio (sin --confirmar solo muestra qué haría)')
        rev.add_argument('cambio', type=int)
        rev.add_argument('--motivo', default='')
        rev.add_argument('--confirmar', action='store_true')

    def handle(self, *args, **opts):
        accion = opts['accion']
        if accion == 'listar':
            qs = ApiCambio.objects.all()
            if opts['clave']:
                qs = qs.filter(usuario=opts['clave'])
            if opts['entidad']:
                qs = qs.filter(entidad=opts['entidad'])
            if opts['id']:
                qs = qs.filter(entidad_id__startswith=opts['id'])
            for c in qs[:opts['limite']]:
                revertido = f" (revertido por #{c.revertido_por_id})" if c.revertido_por_id else ''
                self.stdout.write(f"#{c.pk:<6} {localtime(c.fecha):%Y-%m-%d %H:%M} {c.usuario:20} {c.accion:18} "
                                  f"{c.entidad} {c.entidad_id}{revertido}")
            return

        cambio = ApiCambio.objects.filter(pk=opts['cambio']).first()
        if cambio is None:
            raise CommandError(f"No existe el cambio #{opts['cambio']}")

        if accion == 'ver':
            self.stdout.write(f"#{cambio.pk} {localtime(cambio.fecha):%Y-%m-%d %H:%M:%S} por {cambio.usuario} "
                              f"({cambio.metodo} {cambio.ruta})")
            self.stdout.write(f"{cambio.accion} {cambio.entidad} {cambio.entidad_id}")
            self.stdout.write(f"antes:   {cambio.antes_data}")
            self.stdout.write(f"después: {cambio.despues_data}")
            if cambio.revertido_por_id:
                self.stdout.write(f"revertido por #{cambio.revertido_por_id}")
            return

        try:
            self.stdout.write(f"Revertir #{cambio.pk}: {describir(cambio)}")
            if not opts['confirmar']:
                self.stdout.write("Sin cambios. Repita con --confirmar para aplicarlo.")
                return
            reversion = revertir(cambio, opts['motivo'])
        except NoReversible as e:
            raise CommandError(str(e))
        self.stdout.write(self.style.SUCCESS(f"Revertido. Registro #{reversion.pk}"))
