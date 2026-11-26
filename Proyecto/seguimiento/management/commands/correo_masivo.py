"""Comunicado por correo a todos los contactos de clientes: un correo por destinatario, sin repetir.

Cada campaña vive en una carpeta (por defecto /srv/ducto/comunicados/<campania>/) con:
    asunto.txt       asunto del correo (una línea)                         <- contenido a entregar
    cuerpo.html      cuerpo HTML; admite {nombre} y {cliente}               <- contenido a entregar
    destinatarios.csv  lista generada con --listar (para revisar)
    enviados.jsonl   bitácora: una línea por correo enviado o fallido. Lo ya enviado no se vuelve a enviar,
                     así se puede detener y retomar sin duplicar.

Uso (en el VPS, desde /srv/sistemaducto/Proyecto):
    env/bin/python manage.py correo_masivo --campania NOMBRE --listar
    env/bin/python manage.py correo_masivo --campania NOMBRE --simular
    env/bin/python manage.py correo_masivo --campania NOMBRE --prueba alguien@ductoproyectos.cl
    env/bin/python manage.py correo_masivo --campania NOMBRE --enviar --confirmar 1539

Cada correo es un mensaje SMTP aparte con un solo destinatario en Para (sin CC ni CCO): nadie ve las direcciones
de los demás. Entre correos hay una pausa y cada ejecución tiene un tope, para respetar los límites de Google
Workspace (~2.000 mensajes diarios por cuenta, compartidos con los correos automáticos de cobranza).
"""
import csv
import fcntl
import html
import json
import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, formatdate
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from seguimiento.servicios import clientes

CARPETA_BASE = '/srv/ducto/comunicados'
ENV_SMTP = '/srv/ducto/jobs/.env'
REMITENTE = 'Ducto Proyectos'
# Respuestas del servidor que indican límite de envío: se detiene y se retoma después (sin duplicar)
CODIGOS_LIMITE = {421, 450, 451, 452, 454}


class SmtpSimulado:
    """Reemplaza al servidor SMTP en --simular: no envía nada, solo registra cada mensaje."""

    def __init__(self):
        self.mensajes = []

    def send_message(self, msg, from_addr=None, to_addrs=None):
        self.mensajes.append((msg, list(to_addrs or [])))

    def quit(self):
        pass


class Command(BaseCommand):
    help = 'Comunicado a todos los contactos de clientes: un correo por destinatario, sin repetir.'

    def add_arguments(self, parser):
        parser.add_argument('--campania', required=True, help='Nombre corto de la campaña (carpeta y bitácora).')
        parser.add_argument('--carpeta', help=f'Carpeta de la campaña (por defecto {CARPETA_BASE}/<campania>).')
        modo = parser.add_mutually_exclusive_group(required=True)
        modo.add_argument('--listar', action='store_true', help='Cuenta los destinatarios y genera destinatarios.csv.')
        modo.add_argument('--simular', action='store_true', help='Arma todos los correos sin enviar ninguno.')
        modo.add_argument('--prueba', metavar='CORREO', help='Envía el correo solo a esta dirección (no cuenta en la campaña).')
        modo.add_argument('--enviar', action='store_true', help='Envío real a los destinatarios pendientes.')
        parser.add_argument('--confirmar', type=int, help='Con --enviar: N° de pendientes, para confirmar el envío real.')
        parser.add_argument('--pausa', type=float, default=4.0, help='Segundos entre correos (por defecto 4).')
        parser.add_argument('--maximo', type=int, default=1500, help='Tope de correos en esta ejecución (por defecto 1500).')
        parser.add_argument('--responder-a', help='Dirección para Responder a (opcional).')
        parser.add_argument('--env', default=ENV_SMTP, help=f'Archivo con SMTP_HOST/PORT/USER/PASS (por defecto {ENV_SMTP}).')

    # ------------------------------------------------------------------ utilidades

    def _carpeta(self, opciones):
        nombre = opciones['campania']
        if not re.fullmatch(r'[A-Za-z0-9_\-]+', nombre):
            raise CommandError('El nombre de la campaña solo puede tener letras, números, - y _.')
        carpeta = Path(opciones['carpeta'] or os.path.join(CARPETA_BASE, nombre))
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta

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

    def _enviados(self, carpeta):
        """Correos ya enviados en esta campaña (según la bitácora)."""
        enviados = set()
        bitacora = carpeta / 'enviados.jsonl'
        if bitacora.exists():
            for linea in bitacora.read_text(encoding='utf-8').splitlines():
                try:
                    reg = json.loads(linea)
                except ValueError:
                    continue
                if reg.get('estado') in ('enviado', 'rechazado'):  # rechazado: dirección inexistente, no se reintenta
                    enviados.add(reg['email'])
        return enviados

    def _registrar(self, carpeta, email, estado, detalle=''):
        with open(carpeta / 'enviados.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps({'fecha': timezone.localtime().strftime('%Y-%m-%d %H:%M:%S'), 'email': email,
                                'estado': estado, 'detalle': detalle}, ensure_ascii=False) + '\n')

    def _smtp_config(self, ruta):
        if os.path.exists(ruta):
            from dotenv import dotenv_values
            valores = dotenv_values(ruta)
        else:
            valores = {}
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

    def _mensaje(self, remitente, destinatario, asunto, cuerpo, responder_a=None):
        """Un mensaje para UN destinatario: solo él en Para, sin CC ni CCO."""
        datos = {'nombre': html.escape(destinatario.get('nombre') or ''),
                 'cliente': html.escape(destinatario.get('cliente') or '')}
        cuerpo_html = cuerpo.replace('{nombre}', datos['nombre']).replace('{cliente}', datos['cliente'])
        texto = re.sub(r'<br\s*/?>|</p>|</div>', '\n', cuerpo_html, flags=re.I)
        texto = html.unescape(re.sub(r'<[^>]+>', '', texto))
        texto = re.sub(r'\n{3,}', '\n\n', texto).strip()
        msg = EmailMessage()
        msg['Subject'] = asunto
        msg['From'] = formataddr((REMITENTE, remitente))
        msg['To'] = destinatario['email']
        if responder_a:
            msg['Reply-To'] = responder_a
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain=remitente.split('@')[-1])
        msg.set_content(texto)
        msg.add_alternative(cuerpo_html, subtype='html')
        return msg

    # ------------------------------------------------------------------ comando

    def handle(self, *args, **o):
        carpeta = self._carpeta(o)
        destinatarios, resumen = clientes.correos_contactos()
        enviados = self._enviados(carpeta)
        pendientes = [d for d in destinatarios if d['email'] not in enviados]

        if o['listar']:
            with open(carpeta / 'destinatarios.csv', 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f, delimiter=';')
                w.writerow(['email', 'nombre', 'cliente', 'contactos_con_este_correo', 'ya_enviado'])
                for d in destinatarios:
                    w.writerow([d['email'], d['nombre'], d['cliente'], d['contactos'], 'SI' if d['email'] in enviados else ''])
            for k, v in resumen.items():
                self.stdout.write(f'{k}: {v}')
            self.stdout.write(f'ya_enviados_en_esta_campania: {len(enviados)}')
            self.stdout.write(f'pendientes: {len(pendientes)}')
            self.stdout.write(f'lista: {carpeta / "destinatarios.csv"}')
            return

        asunto, cuerpo = self._contenido(carpeta)

        if o['prueba']:
            correo = o['prueba'].strip().lower()
            cfg = self._smtp_config(o['env'])
            msg = self._mensaje(cfg['SMTP_USER'], {'email': correo, 'nombre': 'Nombre de prueba', 'cliente': 'Cliente de prueba'},
                                asunto, cuerpo, o['responder_a'])
            servidor = self._conectar(cfg)
            try:
                servidor.send_message(msg, from_addr=cfg['SMTP_USER'], to_addrs=[correo])
            finally:
                servidor.quit()
            self.stdout.write(self.style.SUCCESS(f'Correo de prueba enviado solo a {correo}.'))
            return

        lote = pendientes[:o['maximo']]
        if o['simular']:
            servidor = SmtpSimulado()
            remitente = 'remitente@ductoproyectos.cl'
            for d in lote:
                msg = self._mensaje(remitente, d, asunto, cuerpo, o['responder_a'])
                servidor.send_message(msg, from_addr=remitente, to_addrs=[d['email']])
            uno_a_uno = all(len(to) == 1 and to[0] == m['To'] and not m['Cc'] and not m['Bcc'] for m, to in servidor.mensajes)
            unicos = len({to[0] for _, to in servidor.mensajes}) == len(servidor.mensajes)
            self.stdout.write(f'pendientes: {len(pendientes)} | en esta ejecución (tope {o["maximo"]}): {len(lote)}')
            self.stdout.write(f'mensajes armados: {len(servidor.mensajes)}')
            self.stdout.write(f'cada mensaje con un solo destinatario, sin CC/CCO: {"SI" if uno_a_uno else "NO"}')
            self.stdout.write(f'sin destinatarios repetidos: {"SI" if unicos else "NO"}')
            self.stdout.write(f'tiempo estimado con pausa de {o["pausa"]:g}s: {len(lote) * o["pausa"] / 60:.0f} minutos')
            if servidor.mensajes:
                m = servidor.mensajes[0][0]
                self.stdout.write(f'ejemplo -> Para: {m["To"]} | Asunto: {m["Subject"]}')
            return

        # ---- envío real
        if o['confirmar'] != len(pendientes):
            raise CommandError(f'Para enviar de verdad agregue --confirmar {len(pendientes)} (N° de pendientes).')
        if not lote:
            self.stdout.write('No hay pendientes: la campaña ya se envió completa.')
            return
        bloqueo = open(carpeta / '.enviando.lock', 'w')
        try:
            fcntl.flock(bloqueo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise CommandError('Ya hay un envío en curso para esta campaña.')
        cfg = self._smtp_config(o['env'])
        servidor = self._conectar(cfg)
        enviados_ahora = errores = 0
        try:
            for i, d in enumerate(lote, 1):
                msg = self._mensaje(cfg['SMTP_USER'], d, asunto, cuerpo, o['responder_a'])
                try:
                    try:
                        servidor.send_message(msg, from_addr=cfg['SMTP_USER'], to_addrs=[d['email']])
                    except smtplib.SMTPServerDisconnected:
                        servidor = self._conectar(cfg)
                        servidor.send_message(msg, from_addr=cfg['SMTP_USER'], to_addrs=[d['email']])
                    self._registrar(carpeta, d['email'], 'enviado')
                    enviados_ahora += 1
                except smtplib.SMTPRecipientsRefused as e:
                    self._registrar(carpeta, d['email'], 'rechazado', str(e.recipients)[:300])
                    errores += 1
                except smtplib.SMTPResponseException as e:
                    self._registrar(carpeta, d['email'], 'error', f'{e.smtp_code} {e.smtp_error!r}'[:300])
                    errores += 1
                    if e.smtp_code in CODIGOS_LIMITE or b'5.4.5' in (e.smtp_error or b''):
                        self.stdout.write(self.style.WARNING(f'Límite de envío del servidor ({e.smtp_code}). Se detiene; '
                                                             f'retome más tarde con el mismo comando.'))
                        break
                if i % 50 == 0:
                    self.stdout.write(f'{timezone.localtime():%H:%M:%S} enviados {enviados_ahora}, errores {errores}')
                time.sleep(o['pausa'])
        finally:
            try:
                servidor.quit()
            except Exception:
                pass
            bloqueo.close()
        restantes = len(pendientes) - enviados_ahora
        self.stdout.write(self.style.SUCCESS(f'Enviados en esta ejecución: {enviados_ahora}. Errores: {errores}. '
                                             f'Quedan pendientes: {restantes}.'))
