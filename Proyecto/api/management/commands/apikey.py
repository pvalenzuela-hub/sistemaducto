from django.core.management.base import BaseCommand, CommandError

from api.models import ApiKey


class Command(BaseCommand):
    help = "Administra las API Keys de sistemas externos: crear, listar, revocar."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='accion', required=True)
        crear = sub.add_parser('crear', help='Crea una API Key y la muestra una sola vez')
        crear.add_argument('nombre', help='Nombre del sistema externo')
        sub.add_parser('listar', help='Lista las API Keys')
        revocar = sub.add_parser('revocar', help='Desactiva una API Key')
        revocar.add_argument('nombre')

    def handle(self, *args, **opts):
        accion = opts['accion']
        if accion == 'crear':
            if ApiKey.objects.filter(nombre=opts['nombre']).exists():
                raise CommandError(f"Ya existe una API Key con nombre '{opts['nombre']}'")
            _, raw_key = ApiKey.generar(opts['nombre'])
            self.stdout.write(self.style.SUCCESS(f"API Key creada para '{opts['nombre']}':"))
            self.stdout.write(raw_key)
            self.stdout.write("Guárdala ahora: no se puede volver a mostrar.")
        elif accion == 'listar':
            for k in ApiKey.objects.order_by('nombre'):
                estado = 'activa' if k.activa else 'revocada'
                self.stdout.write(f"{k.nombre:30} {k.prefijo}...  {estado:9} creada={k.creada:%Y-%m-%d} ultimo_uso={k.ultimo_uso or '-'}")
        elif accion == 'revocar':
            n = ApiKey.objects.filter(nombre=opts['nombre']).update(activa=False)
            if not n:
                raise CommandError(f"No existe API Key con nombre '{opts['nombre']}'")
            self.stdout.write(self.style.SUCCESS(f"API Key '{opts['nombre']}' revocada"))
