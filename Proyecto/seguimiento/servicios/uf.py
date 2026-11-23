"""Servicio de UF: valor de la UF por fecha desde tValorUF y, si falta, desde internet.

Fuentes, en orden (si una no responde o no tiene la fecha, se prueba la siguiente):
    1. mindicador.cl   API JSON (https://mindicador.cl/api/uf/dd-mm-aaaa)
    2. findic.cl       API JSON con el mismo formato que mindicador
    3. SII             tabla oficial anual (https://www.sii.cl/valores_y_fechas/uf/ufAAAA.htm)
Lo que se trae de internet se guarda en tValorUF, que es la tabla que usa también el escritorio.
"""
import json
import re
from datetime import date
from urllib.request import Request, urlopen

from ..models import tValorUF

TIMEOUT = 8  # segundos por fuente: si una se cuelga, se pasa pronto a la siguiente
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre']
FUENTES_TEXTO = 'mindicador.cl, findic.cl ni SII'


def _get(url):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (sistemaducto)'})
    with urlopen(req, timeout=TIMEOUT) as response:
        return response.read()


def _serie_json(url):
    """{fecha: valor} de una API con formato mindicador ({'serie': [{'fecha': ..., 'valor': ...}]})."""
    payload = json.loads(_get(url).decode('utf-8'))
    return {date.fromisoformat(item['fecha'][:10]): float(item['valor'])
            for item in payload.get('serie') or [] if item.get('fecha') and item.get('valor') is not None}


def _desde_mindicador(fecha):
    return _serie_json(f'https://mindicador.cl/api/uf/{fecha:%d-%m-%Y}').get(fecha)


def _desde_findic(fecha):
    return _serie_json(f'https://findic.cl/api/uf/{fecha:%d-%m-%Y}').get(fecha)


def _tabla_sii(anio):
    """{fecha: valor} de la tabla anual de UF del SII (solo los días ya publicados)."""
    html = _get(f'https://www.sii.cl/valores_y_fechas/uf/uf{anio}.htm').decode('utf-8', 'replace')
    valores = {}
    for mes, nombre in enumerate(MESES, 1):
        inicio = html.find(f"mes_{nombre}'")
        if inicio < 0:
            inicio = html.find(f'mes_{nombre}"')
        if inicio < 0:
            continue
        fin = html.find('mes_', inicio + 5)
        bloque = html[inicio:fin if fin > 0 else len(html)]
        for dia, valor in re.findall(r'<strong>(\d{1,2})</strong>\s*</th>\s*<td[^>]*>\s*([\d.]+,\d+)\s*</td>', bloque):
            try:
                valores[date(anio, mes, int(dia))] = float(valor.replace('.', '').replace(',', '.'))
            except ValueError:
                continue
    return valores


def _desde_sii(fecha):
    return _tabla_sii(fecha.year).get(fecha)


FUENTES = [('mindicador.cl', _desde_mindicador), ('findic.cl', _desde_findic), ('SII', _desde_sii)]


def desde_internet(fecha):
    """(valor, fuente) de la UF de una fecha, o (None, None) si ninguna fuente la tiene o responde."""
    for nombre, buscar in FUENTES:
        try:
            valor = buscar(fecha)
        except Exception:
            continue
        if valor:
            return valor, nombre
    return None, None


def valor_por_fecha(fecha):
    """UF de la fecha desde tValorUF; si falta, la busca en internet y la guarda. None si no existe."""
    if not fecha:
        return None
    row = tValorUF.objects.filter(Fecha=fecha).values('ValorUF').first()
    if row:
        return row['ValorUF']
    valor, _ = desde_internet(fecha)
    if valor is None:
        return None
    obj, _ = tValorUF.objects.get_or_create(Fecha=fecha, defaults={'ValorUF': valor})
    return obj.ValorUF


def sincronizar_faltantes():
    """Agrega a tValorUF las fechas que falten de la serie reciente (mindicador, si no findic) y, si ninguna de
    las dos responde, de la tabla del SII del año en curso. Devuelve (registros nuevos, fuente)."""
    serie, fuente = {}, None
    for nombre, url in (('mindicador.cl', 'https://mindicador.cl/api/uf'), ('findic.cl', 'https://findic.cl/api/uf')):
        try:
            serie = _serie_json(url)
        except Exception:
            serie = {}
        if serie:
            fuente = nombre
            break
    if not serie:
        try:
            serie, fuente = _tabla_sii(date.today().year), 'SII'
        except Exception:
            return 0, None
    existentes = set(tValorUF.objects.filter(Fecha__in=list(serie)).values_list('Fecha', flat=True))
    nuevos = [tValorUF(Fecha=f, ValorUF=v) for f, v in sorted(serie.items()) if f not in existentes]
    tValorUF.objects.bulk_create(nuevos)
    return len(nuevos), fuente
