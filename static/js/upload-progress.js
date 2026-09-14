(function () {
  "use strict";
  // Barra de progreso simple para el form #upload-form (subida de fotos a un
  // álbum). htmx 1.9.12 reenvía los eventos "progress" del XHR de subida como
  // "htmx:xhr:progress" con detail.loaded/detail.total -- eso cubre la fase
  // de transferencia. Una vez que loaded===total, la request sigue viva
  // mientras el backend procesa (Pillow generando las 3 variantes), así que
  // ese tramo se muestra como "Procesando..." hasta htmx:afterRequest.
  var UPLOAD_FORM_ID = "upload-form";
  var currentXhr = null;

  function els() {
    return {
      container: document.getElementById("upload-progress"),
      fill: document.getElementById("upload-progress-fill"),
      label: document.getElementById("upload-progress-label"),
    };
  }

  function show() {
    var e = els();
    if (!e.container) return;
    e.container.classList.remove("hidden");
    if (e.fill) {
      e.fill.style.width = "0%";
      e.fill.classList.remove("is-indeterminate");
    }
    if (e.label) e.label.textContent = "Subiendo…";
  }

  function hide() {
    var e = els();
    if (!e.container) return;
    e.container.classList.add("hidden");
    if (e.fill) e.fill.classList.remove("is-indeterminate");
    currentXhr = null;
  }

  document.body.addEventListener("htmx:beforeRequest", function (evt) {
    if (evt.target.id !== UPLOAD_FORM_ID) return;
    currentXhr = evt.detail.xhr;
    show();
  });

  document.body.addEventListener("htmx:xhr:progress", function (evt) {
    var e = els();
    if (!e.container || e.container.classList.contains("hidden")) return;
    var loaded = evt.detail.loaded;
    var total = evt.detail.total;
    if (!total) return;
    var pct = Math.min(100, Math.round((loaded / total) * 100));
    if (e.fill) e.fill.style.width = pct + "%";
    if (pct >= 100) {
      if (e.label) e.label.textContent = "Procesando…";
      if (e.fill) e.fill.classList.add("is-indeterminate");
    } else if (e.label) {
      e.label.textContent = "Subiendo… " + pct + "%";
    }
  });

  document.body.addEventListener("htmx:afterRequest", function (evt) {
    if (evt.target.id !== UPLOAD_FORM_ID) return;
    hide();
  });

  document.body.addEventListener("htmx:responseError", function (evt) {
    if (evt.target.id !== UPLOAD_FORM_ID) return;
    hide();
  });

  document.body.addEventListener("htmx:sendError", function (evt) {
    if (evt.target.id !== UPLOAD_FORM_ID) return;
    hide();
  });

  document.addEventListener("click", function (evt) {
    if (evt.target.id !== "upload-cancel-btn") return;
    if (!currentXhr) return;
    if (window.confirm("¿Cancelar la subida en curso?")) {
      currentXhr.abort();
      hide();
    }
  });
})();
