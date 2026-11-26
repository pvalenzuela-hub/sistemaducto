"""Comunicado por correo a todos los contactos de clientes, sin que nadie lo reciba dos veces.

Dos formas de enviar:
    por contacto (por defecto)  un correo por persona, solo ella en Para.
    --por-cliente               un correo por cliente con todos sus contactos en Para (o en CCO con --ocultos).
                                Un correo que figura en varios clientes va solo en uno (servicios.clientes).

Cada campaña vive en una carpeta (por defecto /srv/ducto/comunicados/<campania>/) con:
    asunto.txt       asunto del correo (una línea)
    cuerpo.html      cuerpo HTML. Admite {saludo}, {nombre} y {cliente}:
                       {saludo}  por cliente: "Estimados"; por contacto: "Estimado/a <nombre>" o "Estimados" si
                                 el contacto no tiene nombre
    adjuntos/        archivos que van adjuntos en cada correo (p. ej. un PDF)
    destinatarios*.csv  lista generada con --listar, para revisar
    enviados.jsonl   bitácora: una línea por correo enviado o fallido. A una dirección ya enviada no se le vuelve
                     a enviar (en ningún modo), así se puede detener y retomar sin duplicar.
    modo.txt         forma de envío fijada al primer envío real; no se puede cambiar a mitad de campaña.

Uso (en el VPS, desde /srv/sistemaducto/Proyecto, con /srv/sistemaducto/env/bin/python):
    manage.py correo_masivo --campania NOMBRE [--por-cliente [--ocultos]] --listar
    manage.py correo_masivo --campania NOMBRE [--por-cliente [--ocultos]] --simular
    manage.py correo_masivo --campania NOMBRE [--por-cliente [--ocultos]] --prueba alguien@ductoproyectos.cl
    manage.py correo_masivo --campania NOMBRE [--por-cliente [--ocultos]] --enviar --confirmar N

Cada correo es un mensaje SMTP aparte. Entre correos hay una pausa y cada ejecución tiene un tope, para respetar
los límites de Google Workspace (~2.000 mensajes diarios por cuenta, compartidos con los correos de cobranza).
"""
import csv
import fcntl
import html
import json
import mimetypes
import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from seguimiento.servicios import clientes

CARPETA_BASE = '/srv/ducto/comunicados'
ENV_SMTP = '/srv/ducto/jobs/.env'
REMITENTE = 'Ducto Proyectos'
SALUDO_GRUPAL = 'Estimados'
MAX_ADJUNTOS_MB = 10      # por correo: sobre esto no se envía
AVISO_ADJUNTOS_MB = 3     # sobre esto se advierte: más riesgo de spam y de agotar la cuota diaria
# Respuestas del servidor que indican límite de envío: se detiene y se retoma después (sin duplicar)
CODIGOS_LIMITE = {421, 450, 451, 452, 454}


class SmtpSimulado:
    """Reemplaza al servidor SMTP en --simular: no envía nada, solo registra cada mensaje."""

    def __init__(self):
        self.mensajes = []

    def send_message(self, msg, from_addr=None, to_addrs=None):
        self.mensajes.append((msg, list(to_addrs or [])))
        return {}

    def quit(self):
        pass


class Command(BaseCommand):
    help = 'Comunicado a todos los contactos de clientes (por contacto o por cliente), sin repetir.'

    def add_arguments(self, parser):
        parser.add_argument('--campania', required=True, help='Nombre corto de la campaña (carpeta y bitácora).')
        parser.add_argument('--carpeta', help=f'Carpeta de la campaña (por defecto {CARPETA_BASE}/<campania>).')
        parser.add_argument('--por-cliente', action='store_true', help='Un correo por cliente con todos sus contactos.')
        parser.add_argument('--ocultos', action='store_true', help='Con --por-cliente: contactos en CCO en vez de Para.')
        modo = parser.add_mutually_exclusive_group(required=True)
        modo.add_argument('--listar', action='store_true', help='Cuenta los destinatarios y genera el CSV para revisar.')
        modo.add_argument('--simular', action='store_true', help='Arma todos los correos sin enviar ninguno.')
        modo.add_argument('--prueba', metavar='CORREO', help='Envía un correo de muestra solo a esta dirección.')
        modo.add_argument('--enviar', action='store_true', help='Envío real de los correos pendientes.')
        parser.add_argument('--confirmar', type=int, help='Con --enviar: N° de correos pendientes, para confirmar.')
        parser.add_argument('--pausa', type=float, default=4.0, help='Segundos entre correos (por defecto 4).')
        parser.add_argument('--maximo', type=int, default=1500, help='Tope de correos en esta ejecución (por defecto 1500).')
        parser.add_argument('--responder-a', help='Dirección para Responder a (opcional).')
        parser.add_argument('--nombre-remitente', default=REMITENTE,
                            help=f'Nombre visible del remitente (por defecto "{REMITENTE}").')
        parser.add_argument('--env', default=ENV_SMTP, help=f'Archivo con SMTP_HOST/PORT/USER/PASS (por defecto {ENV_SMTP}).')

    # ------------------------------------------------------------------ campaña y contenido

    def _carpeta(self, o):
        nombre = o['campania']
        if not re.fullmatch(r'[A-Za-z0-9_\-]+', nombre):
            raise CommandError('El nombre de la campaña solo puede tener letras, números, - y _.')
        carpeta = Path(o['carpeta'] or os.path.join(CARPETA_BASE, nombre))
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta

    def _forma(self, o):
        if o['ocultos'] and not o['por_cliente']:
            raise CommandError('--ocultos solo se usa con --por-cliente.')
        return ('por-cliente-cco' if o['ocultos'] else 'por-cliente') if o['por_cliente'] else 'por-contacto'

    def _contenido(self, carpeta):
        asunto_f, cuerpo_f = carpeta / 'asunto.txt', carpeta / 'cuerpo.html'
        if not asunto_f.exists() or not cuerpo_f.exists():
            raise CommandError(f'Falta el contenido del correo: deje asunto.txt y cuerpo.html en {carpeta}.')
        lineas = asunto_f.read_text(encoding='utf-8').strip().splitlines()
        asunto = lineas[0].strip() if lineas else ''
        cuerpo = cuerpo_f.read_text(encoding='utf-8').strip()
        if not asunto or not cuerpo:
            raise CommandError('asunto.txt y cuerpo.html no pueden estar vacíos.')
        return asunto, cuerpo

    def _adjuntos(self, carpeta):
        """[(nombre, tipo, subtipo, bytes)] de los archivos en <carpeta>/adjuntos/ (orden alfabético)."""
        adjuntos = []
        dir_adj = carpeta / 'adjuntos'
        if dir_adj.is_dir():
            for f in sorted(dir_adj.iterdir()):
                if not f.is_file() or f.name.startswith('.'):
                    continue
                tipo = mimetypes.guess_type(f.name)[0] or 'application/octet-stream'
                principal, sub = tipo.split('/', 1)
                adjuntos.append((f.name, principal, sub, f.read_bytes()))
        total_mb = sum(len(a[3]) for a in adjuntos) / 1024 / 1024
        if total_mb > MAX_ADJUNTOS_MB:
            raise CommandError(f'Los adjuntos pesan {total_mb:.1f} MB; el máximo por correo es {MAX_ADJUNTOS_MB} MB.')
        return adjuntos

    # ------------------------------------------------------------------ destinatarios y bitácora

    def _bitacora(self, carpeta):
        """Direcciones ya resueltas en esta campaña: enviadas o rechazadas por inexistentes (no se reintentan)."""
        hechos = set()
        archivo = carpeta / 'enviados.jsonl'
        if archivo.exists():
            for linea in archivo.read_text(encoding='utf-8').splitlines():
                try:
                    reg = json.loads(linea)
                except ValueError:
                    continue
                if reg.get('estado') in ('enviado', 'rechazado'):
                    hechos.update(reg.get('emails') or [reg.get('email')])
        return hechos

    def _registrar(self, carpeta, envio, estado, detalle='', emails=None):
        with open(carpeta / 'enviados.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps({'fecha': timezone.localtime().strftime('%Y-%m-%d %H:%M:%S'), 'clave': envio['clave'],
                                'emails': emails if emails is not None else envio['emails'], 'estado': estado,
                                'detalle': detalle}, ensure_ascii=False) + '\n')

    def _envios(self, forma):
        """Lista de envíos: cada uno es un correo con su(s) destinatario(s) y los datos para personalizarlo."""
        if forma == 'por-contacto':
            lista, resumen = clientes.correos_contactos()
            envios = [{'clave': d['email'], 'emails': [d['email']], 'nombre': d['nombre'], 'cliente': d['cliente'],
                       'saludo': f"Estimado/a {d['nombre']}" if d['nombre'] else SALUDO_GRUPAL} for d in lista]
        else:
            lista, resumen = clientes.correos_por_cliente()
            envios = [{'clave': e['clave'], 'emails': e['emails'], 'nombre': '', 'cliente': e['cliente'],
                       'saludo': SALUDO_GRUPAL} for e in lista]
        return envios, resumen

    def _pendientes(self, envios, hechos):
        """Envíos con sus direcciones aún no enviadas (nadie recibe dos veces, aunque se retome)."""
        pendientes = []
        for e in envios:
            faltan = [m for m in e['emails'] if m not in hechos]
            if faltan:
                pendientes.append({**e, 'emails': faltan})
        return pendientes

    # ------------------------------------------------------------------ SMTP y mensaje

    def _smtp_config(self, ruta):
        valores = {}
        if os.path.exists(ruta):
            from dotenv import dotenv_values
            valores = dotenv_values(ruta)
        cfg = {k: os.environ.get(k) or valores.get(k) for k in ('SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASS')}
        if not cfg['SMTP_USER'] or not cfg['SMTP_PASS']:
            raise CommandError(f'Faltan SMTP_USER / SMTP_PASS (archivo {ruta}).')
        cfg['SMTP_HOST'] = cfg['SMTP_HOST'] or 'smtp.gmail.com'
        cfg['SMTP_PORT'] = int(cfg['SMTP_PORT'] or 465)
        return cfg

    def _conectar(self, cfg):
        servidor = smtplib.SMTP_SSL(cfg['SMTP_HOST'], cfg['SMTP_PORT'], context=ssl.create_default_context(), timeout=60)
        servidor.login(cfg['SMTP_USER'], cfg['SMTP_PASS'])
        return servidor

    def _mensaje(self, remitente, envio, asunto, cuerpo, responder_a=None, adjuntos=(), ocultos=False,
                 nombre_remitente=REMITENTE):
        """Un mensaje por envío. Por contacto: solo esa persona en Para. Por cliente: sus contactos en Para, o en CCO
        (en Para queda la cuenta que envía y las direcciones van solo en el sobre SMTP, no en los encabezados)."""
        valores = {k: html.escape(envio.get(k) or '') for k in ('saludo', 'nombre', 'cliente')}
        cuerpo_html = cuerpo
        for k, v in valores.items():
            cuerpo_html = cuerpo_html.replace('{' + k + '}', v)
        texto = re.sub(r'<br\s*/?>|</p>|</div>', '\n', cuerpo_html, flags=re.I)
        texto = html.unescape(re.sub(r'<[^>]+>', '', texto))
        texto = re.sub(r'\n{3,}', '\n\n', texto).strip()
        msg = EmailMessage()
        msg['Subject'] = asunto
        msg['From'] = formataddr((nombre_remitente, remitente))
        msg['To'] = remitente if ocultos else ', '.join(envio['emails'])
        if responder_a:
            msg['Reply-To'] = responder_a
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain=remitente.split('@')[-1])
        msg.set_content(texto)
        msg.add_alternative(cuerpo_html, subtype='html')
        for nombre, principal, sub, datos in adjuntos:
            msg.add_attachment(datos, maintype=principal, subtype=sub, filename=nombre)
        return msg

    # ------------------------------------------------------------------ comando

    def handle(self, *args, **o):
        carpeta = self._carpeta(o)
        forma = self._forma(o)
        ocultos = forma == 'por-cliente-cco'
        fijada = (carpeta / 'modo.txt').read_text().strip() if (carpeta / 'modo.txt').exists() else ''
        if fijada and fijada != forma and not o['listar']:
            raise CommandError(f'Esta campaña ya se empezó a enviar en modo "{fijada}"; no se puede cambiar a "{forma}".')
        envios, resumen = self._envios(forma)
        hechos = self._bitacora(carpeta)
        pendientes = self._pendientes(envios, hechos)

        if o['listar']:
            nombre_csv = 'destinatarios.csv' if forma == 'por-contacto' else 'destinatarios_por_cliente.csv'
            with open(carpeta / nombre_csv, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f, delimiter=';')
                w.writerow(['correo_n', 'cliente', 'saludo', 'cantidad_destinatarios', 'destinatarios', 'ya_enviado'])
                for i, e in enumerate(envios, 1):
                    w.writerow([i, e['cliente'], e['saludo'], len(e['emails']), ', '.join(e['emails']),
                                'SI' if all(m in hechos for m in e['emails']) else ''])
            self.stdout.write(f'forma de envío: {forma}')
            for k, v in resumen.items():
                self.stdout.write(f'{k}: {v}')
            self.stdout.write(f'correos a enviar: {len(envios)} | ya enviados: {len(envios) - len(pendientes)} | '
                              f'pendientes: {len(pendientes)}')
            self.stdout.write(f'lista: {carpeta / nombre_csv}')
            return

        asunto, cuerpo = self._contenido(carpeta)
        adjuntos = self._adjuntos(carpeta)

        if o['prueba']:
            correo = o['prueba'].strip().lower()
            cfg = self._smtp_config(o['env'])
            muestra = envios[0] if envios else {'cliente': 'Cliente de prueba', 'nombre': 'Nombre de prueba',
                                                'saludo': SALUDO_GRUPAL}
            muestra = {**muestra, 'clave': 'prueba', 'emails': [correo]}
            msg = self._mensaje(cfg['SMTP_USER'], muestra, asunto, cuerpo, o['responder_a'], adjuntos, ocultos, o['nombre_remitente'])
            servidor = self._conectar(cfg)
            try:
                servidor.send_message(msg, from_addr=cfg['SMTP_USER'], to_addrs=[correo])
            finally:
                servidor.quit()
            self.stdout.write(self.style.SUCCESS(f'Correo de prueba ({forma}, datos de "{muestra["cliente"]}") '
                                                 f'enviado desde {cfg["SMTP_USER"]} solo a {correo}.'))
            return

        lote = pendientes[:o['maximo']]
        if o['simular']:
            self._simular(forma, ocultos, pendientes, lote, asunto, cuerpo, adjuntos, o)
            return

        # ---- envío real
        if o['confirmar'] != len(pendientes):
            raise CommandError(f'Para enviar de verdad agregue --confirmar {len(pendientes)} (correos pendientes, '
                               f'forma {forma}).')
        if not lote:
            self.stdout.write('No hay pendientes: la campaña ya se envió completa.')
            return
        bloqueo = open(carpeta / '.enviando.lock', 'w')
        try:
            fcntl.flock(bloqueo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise CommandError('Ya hay un envío en curso para esta campaña.')
        (carpeta / 'modo.txt').write_text(forma)
        cfg = self._smtp_config(o['env'])
        servidor = self._conectar(cfg)
        enviados = errores = 0
        try:
            for i, e in enumerate(lote, 1):
                msg = self._mensaje(cfg['SMTP_USER'], e, asunto, cuerpo, o['responder_a'], adjuntos, ocultos, o['nombre_remitente'])
                try:
                    try:
                        rechazados = servidor.send_message(msg, from_addr=cfg['SMTP_USER'], to_addrs=e['emails'])
                    except smtplib.SMTPServerDisconnected:
                        servidor = self._conectar(cfg)
                        rechazados = servidor.send_message(msg, from_addr=cfg['SMTP_USER'], to_addrs=e['emails'])
                    rechazados = rechazados or {}
                    aceptados = [m for m in e['emails'] if m not in rechazados]
                    self._registrar(carpeta, e, 'enviado', emails=aceptados)
                    if rechazados:
                        self._registrar(carpeta, e, 'rechazado', str(rechazados)[:300], emails=list(rechazados))
                    enviados += 1
                except smtplib.SMTPRecipientsRefused as err:
                    self._registrar(carpeta, e, 'rechazado', str(err.recipients)[:300])
                    errores += 1
                except smtplib.SMTPResponseException as err:
                    self._registrar(carpeta, e, 'error', f'{err.smtp_code} {err.smtp_error!r}'[:300])
                    errores += 1
                    if err.smtp_code in CODIGOS_LIMITE or b'5.4.5' in (err.smtp_error or b''):
                        self.stdout.write(self.style.WARNING(f'Límite de envío del servidor ({err.smtp_code}). Se detiene; '
                                                             f'retome más tarde con el mismo comando.'))
                        break
                if i % 50 == 0:
                    self.stdout.write(f'{timezone.localtime():%H:%M:%S} enviados {enviados}, errores {errores}')
                time.sleep(o['pausa'])
        finally:
            try:
                servidor.quit()
            except Exception:
                pass
            bloqueo.close()
        self.stdout.write(self.style.SUCCESS(f'Enviados en esta ejecución: {enviados}. Errores: {errores}. '
                                             f'Quedan pendientes: {len(pendientes) - enviados}.'))

    def _simular(self, forma, ocultos, pendientes, lote, asunto, cuerpo, adjuntos, o):
        servidor = SmtpSimulado()
        remitente = 'remitente@ductoproyectos.cl'
        for e in lote:
            msg = self._mensaje(remitente, e, asunto, cuerpo, o['responder_a'], adjuntos, ocultos, o['nombre_remitente'])
            servidor.send_message(msg, from_addr=remitente, to_addrs=e['emails'])
        vistos = [m for _, to in servidor.mensajes for m in to]
        sin_cc = all(not m['Cc'] and not m['Bcc'] for m, _ in servidor.mensajes)
        if forma == 'por-contacto':
            separacion = all(len(to) == 1 and m['To'] == to[0] for m, to in servidor.mensajes)
            texto_sep = 'cada correo con un solo destinatario'
        elif ocultos:
            separacion = all(m['To'] == remitente and not any(d in str(m) for d in to) for m, to in servidor.mensajes)
            texto_sep = 'contactos solo en CCO (no aparecen en el correo)'
        else:
            separacion = all(sorted(a.strip() for a in m['To'].split(',')) == sorted(to) for m, to in servidor.mensajes)
            texto_sep = 'cada correo solo con los contactos de su cliente en Para'
        con_adjuntos = all(sorted(p.get_filename() for p in m.iter_attachments()) == sorted(a[0] for a in adjuntos)
                           for m, _ in servidor.mensajes)
        saludo_ok = all(m.get_body(('plain',)).get_content().strip().startswith(SALUDO_GRUPAL)
                        for m, _ in servidor.mensajes) if forma != 'por-contacto' and '{saludo}' in cuerpo else None
        self.stdout.write(f'forma de envío: {forma}')
        self.stdout.write(f'correos pendientes: {len(pendientes)} | en esta ejecución (tope {o["maximo"]}): {len(lote)}')
        self.stdout.write(f'correos armados: {len(servidor.mensajes)} | direcciones: {len(vistos)}')
        self.stdout.write(f'{texto_sep}, sin CC: {"SI" if separacion and sin_cc else "NO"}')
        self.stdout.write(f'ninguna dirección repetida: {"SI" if len(set(vistos)) == len(vistos) else "NO"}')
        if saludo_ok is not None:
            self.stdout.write(f'todos comienzan con "{SALUDO_GRUPAL}": {"SI" if saludo_ok else "NO"}')
        if adjuntos:
            mb = sum(len(a[3]) for a in adjuntos) / 1024 / 1024
            self.stdout.write('adjuntos: ' + ', '.join(f'{a[0]} ({len(a[3]) / 1024:.0f} KB)' for a in adjuntos)
                              + f' | en todos los correos: {"SI" if con_adjuntos else "NO"}')
            self.stdout.write(f'volumen total ~{len(servidor.mensajes) * mb:.0f} MB')
            if mb > AVISO_ADJUNTOS_MB:
                self.stdout.write(self.style.WARNING(f'Adjuntos sobre {AVISO_ADJUNTOS_MB} MB: conviene achicarlos.'))
        else:
            self.stdout.write('adjuntos: ninguno')
        self.stdout.write(f'tiempo estimado con pausa de {o["pausa"]:g}s: {len(lote) * o["pausa"] / 60:.0f} minutos')
        if servidor.mensajes:
            m = max(servidor.mensajes, key=lambda x: len(x[1]))[0]
            self.stdout.write(f'ejemplo (el más grande) -> Para: {m["To"][:120]} | Asunto: {m["Subject"]}')
