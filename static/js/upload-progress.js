(function () {
  "use strict";
  // Sube las fotos de a una (no todas en un solo POST multipart) para poder
  // mostrar "foto X de Y" y un progreso real, y para que "Cancelar" pueda
  // cortar la cola entre archivos. Cada POST a /admin/photos ya devuelve el
  // grid actualizado del álbum (ver _render_photo_grid en admin_router.py),
  // así que cada foto aparece apenas termina de procesarse en el server.

  var queue = null; // { files, index, total, albumId, cancelled, xhr }

  function els() {
    return {
      container: document.getElementById("upload-progress"),
      fill: document.getElementById("upload-progress-fill"),
      label: document.getElementById("upload-progress-label"),
    };
  }

  function show() {
    var e = els();
    if (e.container) e.container.classList.remove("hidden");
  }

  function hide() {
    var e = els();
    if (!e.container) return;
    e.container.classList.add("hidden");
    if (e.fill) {
      e.fill.style.width = "0%";
      e.fill.classList.remove("is-indeterminate");
    }
  }

  function setProgress(index, total, filePct, processing) {
    var e = els();
    if (!e.fill || !e.label) return;
    var overall = ((index - 1 + filePct) / total) * 100;
    e.fill.style.width = Math.min(100, Math.max(0, Math.round(overall))) + "%";
    e.fill.classList.toggle("is-indeterminate", processing);
    var suffix = total > 1 ? " -- foto " + index + " de " + total : "";
    e.label.textContent = processing
      ? "Procesando…" + suffix
      : "Subiendo… " + Math.round(filePct * 100) + "%" + suffix;
  }

  function swapGrid(html) {
    if (!html) return;
    var grid = document.getElementById("album-photo-grid") || document.getElementById("photo-grid");
    if (!grid) return;
    var id = grid.id;
    grid.outerHTML = html;
    // htmx solo procesa (activa hx-*) el contenido que ÉL mismo inserta; acá
    // insertamos a mano, así que hay que pedirle explícitamente que lo revise.
    var fresh = document.getElementById(id);
    if (fresh && window.htmx) window.htmx.process(fresh);
  }

  function finish() {
    queue = null;
    hide();
  }

  function uploadNext() {
    if (!queue || queue.cancelled) return finish();
    if (queue.index >= queue.total) return finish();

    var file = queue.files[queue.index];
    var displayIndex = queue.index + 1;
    queue.index += 1;

    var xhr = new XMLHttpRequest();
    queue.xhr = xhr;

    xhr.upload.addEventListener("progress", function (evt) {
      if (!evt.lengthComputable || !queue || queue.cancelled) return;
      setProgress(displayIndex, queue.total, evt.loaded / evt.total, evt.loaded >= evt.total);
    });

    xhr.addEventListener("load", function () {
      if (!queue || queue.cancelled) return;
      if (xhr.status >= 200 && xhr.status < 300) {
        swapGrid(xhr.responseText);
      }
      uploadNext();
    });

    xhr.addEventListener("error", uploadNext);
    xhr.addEventListener("abort", function () {}); // el cleanup lo hace cancelUpload()

    var formData = new FormData();
    formData.append("album_id", String(queue.albumId));
    formData.append("files", file);
    setProgress(displayIndex, queue.total, 0, false);
    xhr.open("POST", "/admin/photos");
    xhr.send(formData);
  }

  function cancelUpload() {
    if (!queue) return;
    if (!window.confirm("¿Cancelar la subida en curso?")) return;
    queue.cancelled = true;
    if (queue.xhr) queue.xhr.abort();
    finish();
  }

  window.pfUploadFiles = function (fileList, albumId) {
    var files = Array.prototype.slice.call(fileList || []);
    if (!files.length) return;
    queue = { files: files, index: 0, total: files.length, albumId: albumId, cancelled: false, xhr: null };
    show();
    uploadNext();
  };

  document.addEventListener("click", function (evt) {
    if (evt.target.id !== "upload-cancel-btn") return;
    cancelUpload();
  });
})();
