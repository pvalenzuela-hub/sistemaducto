from django.core.management.base import BaseCommand, CommandError

from api.models import ApiKey

SI_NO = ['si', 'no']


class Command(BaseCommand):
    help = ("Administra las API Keys de sistemas externos: crear, listar, permisos, revocar. "
            "Toda clave activa puede leer; 'comentar' y 'editar' se habilitan por separado.")

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='accion', required=True)
        crear = sub.add_parser('crear', help='Crea una API Key y la muestra una sola vez')
        crear.add_argument('nombre', help='Nombre del sistema externo (aparece como autor "api:<nombre>")')
        crear.add_argument('--comentar', action='store_true', help='Permite agregar y editar comentarios')
        crear.add_argument('--editar', action='store_true', help='Permite cambiar estados de facturas y proyectos')
        permisos = sub.add_parser('permisos', help='Cambia los permisos de una API Key')
        permisos.add_argument('nombre')
        permisos.add_argument('--comentar', choices=SI_NO)
        permisos.add_argument('--editar', choices=SI_NO)
        sub.add_parser('listar', help='Lista las API Keys')
        revocar = sub.add_parser('revocar', help='Desactiva una API Key')
        revocar.add_argument('nombre')

    def handle(self, *args, **opts):
        accion = opts['accion']
        if accion == 'crear':
            if ApiKey.objects.filter(nombre=opts['nombre']).exists():
                raise CommandError(f"Ya existe una API Key con nombre '{opts['nombre']}'")
            key, raw_key = ApiKey.generar(opts['nombre'], comentar=opts['comentar'], editar=opts['editar'])
            self.stdout.write(self.style.SUCCESS(f"API Key creada para '{key.nombre}' ({key.permisos_texto}):"))
            self.stdout.write(raw_key)
            self.stdout.write("Guárdala ahora: no se puede volver a mostrar.")
        elif accion == 'listar':
            for k in ApiKey.objects.order_by('nombre'):
                estado = 'activa' if k.activa else 'revocada'
                self.stdout.write(f"{k.nombre:30} {k.prefijo}...  {estado:9} {k.permisos_texto:26} "
                                  f"creada={k.creada:%Y-%m-%d} ultimo_uso={k.ultimo_uso or '-'}")
        elif accion == 'permisos':
            cambios = {p: opts[p] == 'si' for p in ('comentar', 'editar') if opts[p]}
            if not cambios:
                raise CommandError("Indique --comentar si|no y/o --editar si|no")
            if not ApiKey.objects.filter(nombre=opts['nombre']).update(**cambios):
                raise CommandError(f"No existe API Key con nombre '{opts['nombre']}'")
            key = ApiKey.objects.get(nombre=opts['nombre'])
            self.stdout.write(self.style.SUCCESS(f"API Key '{key.nombre}': {key.permisos_texto}"))
        elif accion == 'revocar':
            if not ApiKey.objects.filter(nombre=opts['nombre']).update(activa=False):
                raise CommandError(f"No existe API Key con nombre '{opts['nombre']}'")
            self.stdout.write(self.style.SUCCESS(f"API Key '{opts['nombre']}' revocada"))
