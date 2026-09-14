(function () {
  "use strict";
  // Reusa el mismo endpoint que el menú táctil de /display (static/js/display.js
  // -> sendPowerAction). No requiere el código de invitación (POST /api/display/
  // power-action ya es público, mismo modelo de confianza documentado en
  // CLAUDE.md) -- estar detrás del login de /admin es una comodidad extra, no
  // lo que hace segura la acción.
  var MESSAGES = {
    shutdown: "Apagando… esperá unos segundos antes de desconectar la Pi.",
    reboot: "Reiniciando…",
    hide: "Kiosco oculto un rato -- se vuelve a mostrar solo.",
  };

  document.addEventListener("click", function (evt) {
    var btn = evt.target.closest("[data-power-action]");
    if (!btn) return;

    var confirmMsg = btn.dataset.confirm;
    if (confirmMsg && !window.confirm(confirmMsg)) return;

    var action = btn.dataset.powerAction;
    var payload = { action: action };
    if (btn.dataset.hideSeconds) {
      payload.hide_seconds = parseInt(btn.dataset.hideSeconds, 10);
    }

    var feedback = document.getElementById("power-feedback");

    fetch("/api/display/power-action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("bad status");
        if (feedback) feedback.textContent = MESSAGES[action] || "Listo.";
        if (action === "shutdown" || action === "reboot") {
          document.querySelectorAll("[data-power-action]").forEach(function (b) {
            b.disabled = true;
          });
        }
      })
      .catch(function () {
        if (feedback) {
          feedback.textContent = "No se pudo enviar la acción. Revisá la conexión con el backend.";
        }
      });
  });
})();
