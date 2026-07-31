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
    const toastStack = document.getElementById("toast-stack");

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

    // ---- Toasts (avisos de éxito/error visibles en cualquier página) ----
    function mostrarToast(tipo, mensaje) {
        if (!toastStack) return;
        const toast = document.createElement("div");
        toast.className = `toast toast-${tipo}`;
        toast.textContent = mensaje;
        toastStack.appendChild(toast);
        setTimeout(() => {
            toast.classList.add("toast-saliendo");
            setTimeout(() => toast.remove(), 300);
        }, 7000);
        toast.addEventListener("click", () => {
            toast.classList.add("toast-saliendo");
            setTimeout(() => toast.remove(), 300);
        });
    }

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

    socket.on("proceso_estado", (data) => {
        if (!estadoPill) return;
        if (data.corriendo) {
            estadoPill.classList.add("corriendo");
            estadoTexto.textContent = "Procesando…";
            if (btnProcesar) btnProcesar.disabled = true;
        } else {
            estadoPill.classList.remove("corriendo");
            estadoTexto.textContent = "En espera";
            if (btnProcesar) btnProcesar.disabled = false;
        }
    });

    // ---- Logs ----
    if (logPanel) {
        fetch("/api/logs").then(r => r.json()).then(lineas => {
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
        progresoLista.innerHTML = "";
        claves.forEach(key => {
            const p = progresos[key];
            const fila = document.createElement("div");
            fila.className = "progress-row";
            fila.innerHTML = `
                <div class="progress-label">
                    <span></span>
                    <span class="progress-stage"></span>
                </div>
                <div class="progress-track"><div class="progress-fill"></div></div>`;
            fila.querySelector(".progress-label span").textContent = `${p.archivo} · ${p.carpeta}`;
            fila.querySelector(".progress-stage").textContent = `${p.etapa} · ${p.porcentaje}%`;
            fila.querySelector(".progress-fill").style.width = `${p.porcentaje}%`;
            progresoLista.appendChild(fila);
        });
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
        cargarHistorial();
        mostrarToast("success", `✅ Video subido: ${data.archivo}`);
    });

    socket.on("error", (data) => {
        if (data.archivo) {
            const key = `${data.carpeta}::${data.archivo}`;
            delete progresos[key];
            renderProgreso();
        }
        const detalle = data.archivo ? `${data.archivo}: ${data.mensaje}` : data.mensaje;
        mostrarToast("error", `❌ ${detalle}`);
    });

    // =========================================================
    // Historial: búsqueda + paginación (servidor)
    // =========================================================
    let historialPagina = 1;
    let historialQuery = "";
    let historialDebounce = null;

    const historialBody = document.getElementById("historial-body");
    const historialBuscar = document.getElementById("historial-buscar");
    const historialInfo = document.getElementById("historial-info");
    const historialVacio = document.getElementById("historial-vacio");
    const historialAnterior = document.getElementById("historial-anterior");
    const historialSiguiente = document.getElementById("historial-siguiente");

    function construirFilaHistorial(s) {
        const fila = document.createElement("tr");

        const tdArchivo = document.createElement("td");
        tdArchivo.textContent = s.nombre_archivo;
        if (s.nombre_original && s.nombre_original !== s.nombre_archivo) {
            const sub = document.createElement("div");
            sub.className = "fila-original";
            sub.textContent = `Original: ${s.nombre_original}`;
            tdArchivo.appendChild(sub);
        }

        const tdCarpeta = document.createElement("td");
        tdCarpeta.textContent = s.carpeta || "—";

        const tdVideo = document.createElement("td");
        tdVideo.className = "mono";
        if (s.youtube_id) {
            const a = document.createElement("a");
            a.href = `https://youtu.be/${s.youtube_id}`;
            a.target = "_blank";
            a.rel = "noopener";
            a.textContent = `youtu.be/${s.youtube_id}`;
            tdVideo.appendChild(a);
        } else {
            tdVideo.textContent = "—";
        }

        const tdUsuario = document.createElement("td");
        tdUsuario.className = "mono";
        tdUsuario.textContent = s.subido_por || "—";

        const tdFecha = document.createElement("td");
        tdFecha.className = "mono";
        tdFecha.textContent = s.fecha_subida || "—";

        fila.append(tdArchivo, tdCarpeta, tdVideo, tdUsuario, tdFecha);
        return fila;
    }

    async function cargarHistorial() {
        if (!historialBody) return;
        const params = new URLSearchParams({ q: historialQuery, page: historialPagina, per_page: 10 });
        try {
            const res = await fetch(`/api/subidas?${params.toString()}`);
            const data = await res.json();

            historialBody.innerHTML = "";
            data.items.forEach(s => historialBody.appendChild(construirFilaHistorial(s)));

            historialVacio.hidden = data.items.length !== 0;
            historialBody.parentElement.hidden = data.items.length === 0;

            historialInfo.textContent = data.total === 0
                ? ""
                : `Página ${data.page} de ${data.pages} · ${data.total} resultado${data.total === 1 ? "" : "s"}`;
            historialAnterior.disabled = data.page <= 1;
            historialSiguiente.disabled = data.page >= data.pages;
            historialPagina = data.page;
        } catch (e) {
            // fallo silencioso: se reintenta en la proxima carga/busqueda
        }
    }

    if (historialBuscar) {
        historialBuscar.addEventListener("input", () => {
            clearTimeout(historialDebounce);
            historialDebounce = setTimeout(() => {
                historialQuery = historialBuscar.value.trim();
                historialPagina = 1;
                cargarHistorial();
            }, 300);
        });
    }
    if (historialAnterior) {
        historialAnterior.addEventListener("click", () => {
            if (historialPagina > 1) { historialPagina -= 1; cargarHistorial(); }
        });
    }
    if (historialSiguiente) {
        historialSiguiente.addEventListener("click", () => {
            historialPagina += 1;
            cargarHistorial();
        });
    }

    cargarHistorial();

    function formatearTamano(bytes) {
        if (!bytes) return "";
        const mb = Number(bytes) / (1024 * 1024);
        return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(Number(bytes) / 1024).toFixed(0)} KB`;
    }

    // =========================================================
    // Modal 1: lista de pendientes de una carpeta
    // =========================================================
    const carpetas = window.PALTA_CARPETAS || [];
    const carpetasPorId = {};
    carpetas.forEach(c => { carpetasPorId[c.id] = c; });

    const modalLista = document.getElementById("modal-lista");
    const modalListaTitulo = document.getElementById("modal-lista-titulo");
    const modalListaCargando = document.getElementById("modal-lista-cargando");
    const modalListaVacio = document.getElementById("modal-lista-vacio");
    const modalListaVideos = document.getElementById("modal-lista-videos");
    const modalListaContador = document.getElementById("modal-lista-contador");
    const modalListaContinuar = document.getElementById("modal-lista-continuar");
    const modalListaCancelar = document.getElementById("modal-lista-cancelar");
    const modalListaCerrar = document.getElementById("modal-lista-cerrar");

    let carpetaAbierta = null;

    function abrirModalLista(carpetaId) {
        const carpeta = carpetasPorId[carpetaId];
        if (!carpeta) return;
        carpetaAbierta = carpeta;

        modalListaTitulo.textContent = `Videos pendientes · ${carpeta.nombre}`;
        modalListaVideos.hidden = true;
        modalListaVacio.hidden = true;
        modalListaCargando.hidden = false;
        modalListaVideos.innerHTML = "";
        modalListaContador.textContent = "0 seleccionados";
        modalListaContinuar.disabled = true;
        modalLista.hidden = false;

        fetch(`/api/pendientes/${carpetaId}`)
            .then(r => r.json())
            .then(data => {
                modalListaCargando.hidden = true;
                if (data.error || !data.pendientes || data.pendientes.length === 0) {
                    modalListaVacio.hidden = false;
                    return;
                }
                data.pendientes.forEach(v => {
                    const li = document.createElement("li");
                    li.className = "modal-lista-fila";

                    const label = document.createElement("label");
                    label.className = "chk-label";
                    const chk = document.createElement("input");
                    chk.type = "checkbox";
                    chk.className = "chk-video";
                    label.appendChild(chk);

                    const info = document.createElement("div");
                    info.className = "modal-lista-info";
                    const nombre = document.createElement("div");
                    nombre.className = "modal-lista-nombre";
                    nombre.textContent = v.name;
                    const tamano = document.createElement("div");
                    tamano.className = "modal-lista-tamano";
                    tamano.textContent = formatearTamano(v.size);
                    info.append(nombre, tamano);

                    li.append(label, info);
                    li.dataset.driveId = v.id;
                    li.dataset.nombre = v.name;
                    li.dataset.tituloSugerido = v.titulo_sugerido || v.name;

                    li.addEventListener("click", (e) => {
                        if (e.target !== chk) chk.checked = !chk.checked;
                        actualizarContadorLista();
                    });

                    modalListaVideos.appendChild(li);
                });
                modalListaVideos.hidden = false;
            })
            .catch(() => {
                modalListaCargando.hidden = true;
                modalListaVacio.hidden = false;
                modalListaVacio.textContent = "No se pudo consultar Drive.";
            });
    }

    function actualizarContadorLista() {
        const marcados = modalListaVideos.querySelectorAll(".chk-video:checked").length;
        modalListaContador.textContent = `${marcados} seleccionado${marcados === 1 ? "" : "s"}`;
        modalListaContinuar.disabled = marcados === 0;
    }

    function cerrarModalLista() {
        modalLista.hidden = true;
        carpetaAbierta = null;
    }

    if (modalListaCancelar) modalListaCancelar.addEventListener("click", cerrarModalLista);
    if (modalListaCerrar) modalListaCerrar.addEventListener("click", cerrarModalLista);

    document.querySelectorAll(".folder-card").forEach(card => {
        card.addEventListener("click", () => {
            if (card.disabled) return;
            const carpetaId = Number(card.dataset.carpetaId);
            abrirModalLista(carpetaId);
        });
    });

    // Cargar el conteo de pendientes en cada tarjeta de carpeta al entrar
    carpetas.forEach(c => {
        const card = document.querySelector(`.folder-card[data-carpeta-id="${c.id}"]`);
        const estadoEl = card ? card.querySelector("[data-pendientes]") : null;
        if (!card || !estadoEl) return;

        if (!c.activo) {
            estadoEl.textContent = "Carpeta inactiva";
            card.disabled = true;
            return;
        }

        fetch(`/api/pendientes/${c.id}`)
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    estadoEl.textContent = "No se pudo consultar Drive";
                    card.disabled = true;
                    return;
                }
                const n = data.pendientes.length;
                estadoEl.textContent = n === 0 ? "Sin videos pendientes" : `${n} video${n === 1 ? "" : "s"} pendiente${n === 1 ? "" : "s"}`;
                card.disabled = n === 0;
            })
            .catch(() => {
                estadoEl.textContent = "No se pudo consultar Drive";
                card.disabled = true;
            });
    });

    // =========================================================
    // Modal 2: configuracion por video (wizard)
    // =========================================================
    const modalConfig = document.getElementById("modal-config");
    const modalConfigOriginal = document.getElementById("modal-config-original");
    const inputTitulo = document.getElementById("modal-config-input-titulo");
    const inputDescripcion = document.getElementById("modal-config-input-descripcion");
    const inputPrivacidad = document.getElementById("modal-config-input-privacidad");
    const inputMiniatura = document.getElementById("modal-config-input-miniatura");
    const previewMiniatura = document.getElementById("modal-config-preview-miniatura");
    const modalConfigProgreso = document.getElementById("modal-config-progreso");
    const modalConfigAnterior = document.getElementById("modal-config-anterior");
    const modalConfigSiguiente = document.getElementById("modal-config-siguiente");
    const modalConfigCerrar = document.getElementById("modal-config-cerrar");

    let wizardOrden = [];       // [{carpeta_id, carpeta_nombre, drive_id, nombre, titulo_sugerido}]
    let wizardConfig = {};      // drive_id -> {titulo, descripcion, privacidad, miniaturaFile}
    let wizardIndex = 0;

    function iniciarWizard() {
        const marcados = Array.from(modalListaVideos.querySelectorAll("li")).filter(li =>
            li.querySelector(".chk-video").checked
        );
        if (marcados.length === 0) return;

        wizardOrden = marcados.map(li => ({
            carpeta_id: carpetaAbierta.id,
            carpeta_nombre: carpetaAbierta.nombre,
            drive_id: li.dataset.driveId,
            nombre: li.dataset.nombre,
            titulo_sugerido: li.dataset.tituloSugerido,
        }));

        wizardConfig = {};
        wizardOrden.forEach(v => {
            wizardConfig[v.drive_id] = {
                titulo: v.titulo_sugerido,
                descripcion: "",
                privacidad: "private",
                miniaturaFile: null,
            };
        });

        wizardIndex = 0;
        cerrarModalLista();
        mostrarPasoWizard();
        modalConfig.hidden = false;
    }

    function guardarPasoActual() {
        const v = wizardOrden[wizardIndex];
        if (!v) return;
        wizardConfig[v.drive_id] = {
            titulo: inputTitulo.value.trim().slice(0, 100),
            descripcion: inputDescripcion.value.trim(),
            privacidad: inputPrivacidad.value,
            miniaturaFile: inputMiniatura.files[0] || wizardConfig[v.drive_id].miniaturaFile,
        };
    }

    function restaurarArchivo(inputEl, file) {
        if (!file) { inputEl.value = ""; return; }
        try {
            const dt = new DataTransfer();
            dt.items.add(file);
            inputEl.files = dt.files;
        } catch (e) {
            inputEl.value = "";
        }
    }

    function mostrarPasoWizard() {
        const v = wizardOrden[wizardIndex];
        if (!v) return;
        const cfg = wizardConfig[v.drive_id];

        modalConfigOriginal.textContent = v.nombre;
        inputTitulo.value = cfg.titulo;
        inputDescripcion.value = cfg.descripcion;
        inputPrivacidad.value = cfg.privacidad;
        restaurarArchivo(inputMiniatura, cfg.miniaturaFile);

        if (cfg.miniaturaFile) {
            previewMiniatura.src = URL.createObjectURL(cfg.miniaturaFile);
            previewMiniatura.hidden = false;
        } else {
            previewMiniatura.hidden = true;
        }

        modalConfigProgreso.textContent = `Video ${wizardIndex + 1} de ${wizardOrden.length}`;
        modalConfigAnterior.disabled = wizardIndex === 0;
        modalConfigSiguiente.textContent = wizardIndex === wizardOrden.length - 1 ? "Iniciar subida" : "Siguiente";
    }

    if (inputMiniatura) {
        inputMiniatura.addEventListener("change", () => {
            const file = inputMiniatura.files[0];
            if (file) {
                previewMiniatura.src = URL.createObjectURL(file);
                previewMiniatura.hidden = false;
            } else {
                previewMiniatura.hidden = true;
            }
        });
    }

    if (modalConfigAnterior) {
        modalConfigAnterior.addEventListener("click", () => {
            guardarPasoActual();
            if (wizardIndex > 0) {
                wizardIndex -= 1;
                mostrarPasoWizard();
            }
        });
    }

    if (modalConfigSiguiente) {
        modalConfigSiguiente.addEventListener("click", () => {
            guardarPasoActual();
            if (wizardIndex < wizardOrden.length - 1) {
                wizardIndex += 1;
                mostrarPasoWizard();
            } else {
                finalizarWizard();
            }
        });
    }

    function cerrarModalConfig() {
        modalConfig.hidden = true;
        wizardOrden = [];
        wizardConfig = {};
        wizardIndex = 0;
    }

    if (modalConfigCerrar) modalConfigCerrar.addEventListener("click", cerrarModalConfig);

    if (modalListaContinuar) modalListaContinuar.addEventListener("click", iniciarWizard);

    async function finalizarWizard() {
        const formData = new FormData();
        const items = wizardOrden.map(v => {
            const cfg = wizardConfig[v.drive_id];
            return {
                carpeta_id: v.carpeta_id,
                drive_id: v.drive_id,
                nombre: v.nombre,
                titulo: cfg.titulo,
                descripcion: cfg.descripcion,
                privacidad: cfg.privacidad,
            };
        });
        formData.append("items", JSON.stringify(items));
        wizardOrden.forEach(v => {
            const cfg = wizardConfig[v.drive_id];
            if (cfg.miniaturaFile) {
                formData.append(`thumbnail_${v.drive_id}`, cfg.miniaturaFile);
            }
        });

        cerrarModalConfig();
        if (btnProcesar) btnProcesar.disabled = true;

        try {
            const res = await fetch("/procesar/seleccion", { method: "POST", body: formData });
            if (!res.ok && res.status !== 202) {
                const data = await res.json().catch(() => ({}));
                alert(data.status || "No se pudo iniciar el procesamiento.");
                if (btnProcesar) btnProcesar.disabled = false;
            }
        } catch (e) {
            alert("Error de red al iniciar el procesamiento.");
            if (btnProcesar) btnProcesar.disabled = false;
        }
    }

    // Cerrar modales con Escape
    document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape") return;
        if (modalConfig && !modalConfig.hidden) cerrarModalConfig();
        else if (modalLista && !modalLista.hidden) cerrarModalLista();
    });
});
