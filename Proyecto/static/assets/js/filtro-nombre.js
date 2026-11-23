/* Filtra las filas de una tabla mientras se escribe, buscando el texto (o parte de él) en una columna.
   No distingue mayúsculas ni tildes. Funciona con tablas DataTables y con tablas simples.
   Uso: <input type="search" class="filtro-nombre" data-tabla="#idTabla" data-columna="Proyecto"
               data-contador="#idSpan">
   data-columna es el título de la columna; data-contador (opcional) muestra "N de M" en tablas simples. */
(function () {
    const normalizar = t => (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();

    function indiceColumna(tabla, titulo) {
        const buscado = normalizar(titulo);
        const ths = Array.from(tabla.querySelectorAll('thead tr:last-child th'));
        return ths.findIndex(th => normalizar(th.textContent).replace(/[▲▼]/g, '').trim() === buscado);
    }

    function iniciar(input) {
        const tabla = document.querySelector(input.dataset.tabla);
        if (!tabla) return;
        const idx = indiceColumna(tabla, input.dataset.columna || 'Proyecto');
        if (idx < 0) return;
        const contador = input.dataset.contador ? document.querySelector(input.dataset.contador) : null;
        const columnas = tabla.querySelectorAll('thead tr:last-child th').length;
        let filtroDataTables = false;

        // El tipo de tabla se decide al escribir: DataTables puede inicializarse después que este script.
        input.addEventListener('input', function () {
            const $ = window.jQuery;
            // DataTables con su búsqueda activa: se usa su filtro. Si la tiene desactivada (searching: false), se ocultan las filas.
            const dtConBusqueda = $ && $.fn.dataTable && $.fn.dataTable.isDataTable(tabla) &&
                $(tabla).DataTable().settings()[0].oFeatures.bFilter;
            if (dtConBusqueda) {
                if (!filtroDataTables) {
                    filtroDataTables = true;
                    $.fn.dataTable.ext.search.push(function (settings, datos) {
                        if (settings.nTable !== tabla) return true;
                        const q = normalizar(input.value);
                        if (!q) return true;
                        const celda = document.createElement('div');
                        celda.innerHTML = datos[idx] || '';
                        return normalizar(celda.textContent).includes(q);
                    });
                }
                $(tabla).DataTable().draw();
                return;
            }
            const q = normalizar(input.value);
            let visibles = 0, total = 0;
            Array.from(tabla.tBodies[0].rows).forEach(tr => {
                if (tr.cells.length !== columnas) return;  // filas de "sin datos" o de subtotales
                total++;
                const coincide = !q || normalizar(tr.cells[idx].innerText).includes(q);
                tr.style.display = coincide ? '' : 'none';
                if (coincide) visibles++;
            });
            if (contador) contador.textContent = q ? `${visibles} de ${total}` : '';
        });
    }

    // Después de que las tablas DataTables se inicialicen
    window.addEventListener('load', () => document.querySelectorAll('input.filtro-nombre').forEach(iniciar));
})();
