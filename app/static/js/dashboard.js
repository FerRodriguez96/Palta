document.addEventListener("DOMContentLoaded", () => {
    const socket = io();
    const connDot = document.getElementById("conn-dot");
    const connLabel = document.getElementById("conn-label");
    const btnProcesar = document.getElementById("btn-procesar");
    const estadoPill = document.getElementById("estado-pill");
    const estadoTexto = document.getElementById("estado-texto");
    const logPanel = document.getElementById("log-panel");
    const progresoLista = document.getElementById("progreso-lista");
    const progresoVacio = document.getElementById("progreso-vacio");

    const progresos = {}; // key: carpeta::archivo -> {etapa, porcentaje}

    // ---- Conexión ----
    socket.on("connect", () => {
        connDot.classList.add("ok"); connDot.classList.remove("off");
        connLabel.textContent = "Conectado en vivo";
    });
    socket.on("disconnect", () => {
        connDot.classList.remove("ok"); connDot.classList.add("off");
        connLabel.textContent = "Sin conexión en vivo";
    });

    // ---- Botón procesar todo ----
    if (btnProcesar) {
        btnProcesar.addEventListener("click", async () => {
            btnProcesar.disabled = true;
            try {
                const res = await fetch("/procesar", { method: "POST" });
                if (!res.ok && res.status !== 202) {
                    const data = await res.json().catch(() => ({}));
                    alert(data.status || "No se pudo iniciar el procesamiento.");
                    btnProcesar.disabled = false;
                }
            } catch (e) {
                alert("Error de red al iniciar el procesamiento.");
                btnProcesar.disabled = false;
            }
        });
    }

    // ---- Selección manual de videos (con título editable) ----
    const btnSeleccion = document.getElementById("btn-procesar-seleccion");
    const contadorSeleccion = document.getElementById("contador-seleccion");

    function actualizarContadorSeleccion() {
        const marcados = document.querySelectorAll(".chk-video:checked");
        if (!btnSeleccion) return;
        contadorSeleccion.textContent = marcados.length;
        btnSeleccion.hidden = marcados.length === 0;
    }

    document.addEventListener("change", (e) => {
        if (e.target.classList && e.target.classList.contains("chk-video")) {
            actualizarContadorSeleccion();
        }
    });

    if (btnSeleccion) {
        btnSeleccion.addEventListener("click", async () => {
            const marcados = Array.from(document.querySelectorAll(".chk-video:checked"));
            if (marcados.length === 0) return;

            const items = marcados.map(chk => {
                const li = chk.closest("li");
                const inputTitulo = li ? li.querySelector(".titulo-video") : null;
                const titulo = inputTitulo ? inputTitulo.value.trim().slice(0, 100) : "";
                return {
                    carpeta_id: Number(chk.dataset.carpetaId),
                    drive_id: chk.dataset.driveId,
                    nombre: chk.dataset.nombre,
                    titulo: titulo,
                };
            });

            btnSeleccion.disabled = true;
            if (btnProcesar) btnProcesar.disabled = true;

            try {
                const res = await fetch("/procesar/seleccion", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ items }),
                });
                if (!res.ok && res.status !== 202) {
                    const data = await res.json().catch(() => ({}));
                    alert(data.status || "No se pudo iniciar el procesamiento.");
                    btnSeleccion.disabled = false;
                    if (btnProcesar) btnProcesar.disabled = false;
                } else {
                    marcados.forEach(chk => { chk.checked = false; });
                    actualizarContadorSeleccion();
                }
            } catch (e) {
                alert("Error de red al iniciar el procesamiento.");
                btnSeleccion.disabled = false;
                if (btnProcesar) btnProcesar.disabled = false;
            }
        });
    }

    socket.on("proceso_estado", (data) => {
        if (!estadoPill) return;
        if (data.corriendo) {
            estadoPill.classList.add("corriendo");
            estadoTexto.textContent = "Procesando…";
            if (btnProcesar) btnProcesar.disabled = true;
            if (btnSeleccion) btnSeleccion.disabled = true;
        } else {
            estadoPill.classList.remove("corriendo");
            estadoTexto.textContent = "En espera";
            if (btnProcesar) btnProcesar.disabled = false;
            if (btnSeleccion) btnSeleccion.disabled = false;
        }
    });

    // ---- Logs ----
    if (logPanel) {
        fetch("/logs").then(r => r.json()).then(lineas => {
            lineas.forEach(l => appendLog(l));
        });
    }

    function appendLog(mensaje) {
        if (!logPanel) return;
        const div = document.createElement("div");
        div.textContent = mensaje;
        logPanel.appendChild(div);
        logPanel.scrollTop = logPanel.scrollHeight;
        while (logPanel.children.length > 300) {
            logPanel.removeChild(logPanel.firstChild);
        }
    }

    socket.on("log", (data) => appendLog(data.mensaje));

    // ---- Progreso ----
    function renderProgreso() {
        if (!progresoLista) return;
        const claves = Object.keys(progresos);
        if (claves.length === 0) {
            progresoVacio.style.display = "block";
            progresoLista.innerHTML = "";
            return;
        }
        progresoVacio.style.display = "none";
        progresoLista.innerHTML = claves.map(key => {
            const p = progresos[key];
            return `
                <div class="progress-row">
                    <div class="progress-label">
                        <span>${p.archivo} <span class="progress-stage">· ${p.carpeta}</span></span>
                        <span class="progress-stage">${p.etapa} · ${p.porcentaje}%</span>
                    </div>
                    <div class="progress-track"><div class="progress-fill" style="width:${p.porcentaje}%;"></div></div>
                </div>`;
        }).join("");
    }

    socket.on("progreso", (data) => {
        if (!data.archivo) return;
        const key = `${data.carpeta}::${data.archivo}`;
        progresos[key] = data;
        renderProgreso();
    });

    socket.on("subido", (data) => {
        const key = `${data.carpeta}::${data.archivo}`;
        delete progresos[key];
        renderProgreso();
        prependHistorial(data);
    });

    socket.on("error", (data) => {
        if (data.archivo) {
            const key = `${data.carpeta}::${data.archivo}`;
            delete progresos[key];
            renderProgreso();
        }
    });

    function prependHistorial(data) {
        const body = document.getElementById("historial-body");
        if (!body) return;
        const fila = document.createElement("tr");
        const ahora = new Date().toLocaleString("es-AR");
        const link = data.youtube_id
            ? `<a href="https://youtu.be/${data.youtube_id}" target="_blank" rel="noopener">youtu.be/${data.youtube_id}</a>`
            : "—";
        fila.innerHTML = `
            <td>${data.archivo}</td>
            <td>${data.carpeta}</td>
            <td class="mono">${link}</td>
            <td class="mono">${data.usuario || "—"}</td>
            <td class="mono">${ahora}</td>`;
        body.prepend(fila);
    }

    // ---- Pendientes por carpeta ----
    const carpetas = window.PALTA_CARPETAS || [];

    function formatearTamano(bytes) {
        if (!bytes) return "";
        const mb = Number(bytes) / (1024 * 1024);
        return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(Number(bytes) / 1024).toFixed(0)} KB`;
    }

    carpetas.forEach(c => {
        if (!c.activo) return;
        const boton = document.querySelector(`.folder-card[data-carpeta-id="${c.id}"] [data-pendientes]`);
        const lista = document.querySelector(`.folder-card[data-carpeta-id="${c.id}"] [data-pendientes-list]`);

        fetch(`/api/pendientes/${c.id}`)
            .then(r => r.json())
            .then(data => {
                if (!boton) return;
                if (data.error) {
                    boton.textContent = "No se pudo consultar Drive";
                    boton.disabled = true;
                    return;
                }
                const n = data.pendientes.length;
                boton.textContent = n === 0
                    ? "Sin videos pendientes"
                    : `${n} video${n === 1 ? "" : "s"} pendiente${n === 1 ? "" : "s"} · ver lista`;
                boton.disabled = n === 0;

                if (n > 0 && lista) {
                    lista.innerHTML = data.pendientes.map(v => `
                        <li>
                            <div class="pendiente-fila">
                                <label class="chk-label">
                                    <input type="checkbox" class="chk-video"
                                           data-carpeta-id="${c.id}" data-carpeta-nombre="${c.nombre}"
                                           data-drive-id="${v.id}" data-nombre="${v.name}">
                                </label>
                                <input type="text" class="titulo-video" maxlength="100"
                                       value="${(v.titulo_sugerido || v.name).replace(/"/g, '&quot;')}"
                                       placeholder="Título en YouTube (máx. 100 caracteres)">
                                <span class="tamano">${formatearTamano(v.size)}</span>
                            </div>
                        </li>`).join("");

                    boton.addEventListener("click", () => {
                        const abierto = !lista.hidden;
                        lista.hidden = abierto;
                        boton.textContent = abierto
                            ? `${n} video${n === 1 ? "" : "s"} pendiente${n === 1 ? "" : "s"} · ver lista`
                            : `${n} video${n === 1 ? "" : "s"} pendiente${n === 1 ? "" : "s"} · ocultar lista`;
                    });
                }
            })
            .catch(() => {
                if (boton) {
                    boton.textContent = "No se pudo consultar Drive";
                    boton.disabled = true;
                }
            });
    });
});
