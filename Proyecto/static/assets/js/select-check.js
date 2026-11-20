/* Lista desplegable con casillas para elegir varias opciones.
   Uso: <select name="estado" multiple class="select-check" data-texto="estados" data-defecto="1,2,3">
          <option value="1" data-color="#fff" selected>Proyecto Nuevo</option> ...
        </select>
   El <select multiple> queda oculto y sigue siendo el que se envía en el formulario.
   data-defecto (opcional) agrega el atajo "Por defecto". data-vacio (opcional): texto cuando no hay nada marcado. data-color (opcional) muestra el color de cada opción. */
(function () {
    function crear(select) {
        if (select.dataset.selectCheck === '1') return;
        select.dataset.selectCheck = '1';
        select.style.display = 'none';
        const nombrePlural = select.dataset.texto || 'opciones';
        const defecto = (select.dataset.defecto || '').split(',').map(s => s.trim()).filter(Boolean);
        const opciones = Array.from(select.options);

        const contenedor = document.createElement('div');
        contenedor.className = 'dropdown select-check';
        const boton = document.createElement('button');
        boton.type = 'button';
        boton.className = 'form-select text-start text-truncate';
        boton.setAttribute('data-bs-toggle', 'dropdown');
        boton.setAttribute('data-bs-auto-close', 'outside');
        boton.setAttribute('aria-expanded', 'false');
        const menu = document.createElement('div');
        menu.className = 'dropdown-menu p-2 shadow';
        menu.style.cssText = 'min-width: 100%; max-height: 360px; overflow-y: auto;';

        const atajos = document.createElement('div');
        atajos.className = 'd-flex gap-2 small border-bottom pb-1 mb-1';
        const accionesAtajo = [['Todos', () => true], ['Ninguno', () => false]];
        if (defecto.length) accionesAtajo.unshift(['Por defecto', o => defecto.includes(o.value)]);
        accionesAtajo.forEach(([texto, regla]) => {
            const a = document.createElement('a');
            a.href = '#';
            a.textContent = texto;
            a.addEventListener('click', e => {
                e.preventDefault();
                opciones.forEach(o => { o.selected = regla(o); });
                sincronizar();
            });
            atajos.appendChild(a);
        });
        menu.appendChild(atajos);

        const casillas = opciones.map(o => {
            const etiqueta = document.createElement('label');
            etiqueta.className = 'dropdown-item d-flex align-items-center gap-2 py-1 rounded';
            etiqueta.style.cursor = 'pointer';
            const chk = document.createElement('input');
            chk.type = 'checkbox';
            chk.className = 'form-check-input m-0';
            chk.style.cssText = 'position: static; float: none; flex: none; margin: 0;';  // el tema posiciona las casillas en absoluto
            chk.value = o.value;
            chk.checked = o.selected;
            chk.addEventListener('change', () => { o.selected = chk.checked; actualizarBoton(); });
            etiqueta.appendChild(chk);
            if (o.dataset.color) {
                const punto = document.createElement('span');
                punto.style.cssText = `display:inline-block;width:.8rem;height:.8rem;border-radius:3px;border:1px solid #999;background:${o.dataset.color};flex:none;`;
                etiqueta.appendChild(punto);
            }
            etiqueta.appendChild(document.createTextNode(o.textContent.trim()));
            menu.appendChild(etiqueta);
            return chk;
        });

        function actualizarBoton() {
            const sel = opciones.filter(o => o.selected);
            let texto;
            if (sel.length === 0) texto = select.dataset.vacio || 'Ninguno';  // p. ej. 'Todos' si vacío = sin filtro
            else if (sel.length === opciones.length) texto = 'Todos';
            else if (sel.length <= 2) texto = sel.map(o => o.textContent.trim()).join(', ');
            else texto = `${sel.length} ${nombrePlural} seleccionados`;
            boton.textContent = texto;
            boton.title = sel.map(o => o.textContent.trim()).join('\n');
        }
        function sincronizar() {
            casillas.forEach((chk, i) => { chk.checked = opciones[i].selected; });
            actualizarBoton();
        }

        contenedor.appendChild(boton);
        contenedor.appendChild(menu);
        select.insertAdjacentElement('afterend', contenedor);
        const label = select.id ? document.querySelector(`label[for="${select.id}"]`) : null;
        if (label) label.addEventListener('click', e => { e.preventDefault(); boton.focus(); });
        actualizarBoton();
    }
    function iniciar() { document.querySelectorAll('select.select-check[multiple]').forEach(crear); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
