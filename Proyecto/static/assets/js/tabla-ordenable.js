/* Ordena una tabla al hacer clic en el título de columna, como las grillas del sistema de escritorio.
   Uso: <table class="tabla-ordenable">; las columnas con data-no-ordenar se omiten.
   Reconoce fechas dd/mm/aaaa (con hora opcional), montos ($ 1.234.567 / 12,5) y texto. */
(function () {
    function clave(texto) {
        const t = (texto || '').trim();
        if (!t) return { tipo: 0, v: '' };
        const f = t.match(/^(\d{2})\/(\d{2})\/(\d{4})(?:\s+(\d{2}):(\d{2}))?/);
        if (f) return { tipo: 1, v: Number(f[3] + f[2] + f[1] + (f[4] || '00') + (f[5] || '00')) };
        const n = t.replace(/[$\s%]/g, '');
        if (/^-?[\d.]+(,\d+)?$/.test(n)) return { tipo: 1, v: parseFloat(n.replace(/\./g, '').replace(',', '.')) };
        return { tipo: 2, v: t.toLocaleLowerCase('es') };
    }
    function comparar(a, b) {
        if (a.tipo === 0 || b.tipo === 0) return a.tipo === b.tipo ? 0 : (a.tipo === 0 ? 1 : -1);  // vacíos al final
        if (a.tipo === 1 && b.tipo === 1) return a.v - b.v;
        return String(a.v).localeCompare(String(b.v), 'es', { numeric: true });
    }
    document.querySelectorAll('table.tabla-ordenable').forEach(function (tabla) {
        const ths = tabla.querySelectorAll('thead th');
        ths.forEach(function (th, i) {
            if (th.hasAttribute('data-no-ordenar')) return;
            th.style.cursor = 'pointer';
            th.title = 'Ordenar';
            th.addEventListener('click', function () {
                const tbody = tabla.tBodies[0];
                const filas = Array.from(tbody.rows).filter(r => r.cells.length === ths.length);
                if (filas.length < 2) return;
                const asc = th.getAttribute('data-orden') !== 'asc';
                ths.forEach(x => { x.removeAttribute('data-orden'); x.querySelector('.orden-flecha')?.remove(); });
                th.setAttribute('data-orden', asc ? 'asc' : 'desc');
                th.insertAdjacentHTML('beforeend', '<span class="orden-flecha"> ' + (asc ? '▲' : '▼') + '</span>');
                filas.map(r => ({ r, k: clave(r.cells[i].innerText) }))
                     .sort((a, b) => {
                         if (a.k.tipo === 0 || b.k.tipo === 0) return comparar(a.k, b.k);  // vacíos siempre al final
                         return (asc ? 1 : -1) * comparar(a.k, b.k);
                     })
                     .forEach(x => tbody.appendChild(x.r));
            });
        });
    });
})();
