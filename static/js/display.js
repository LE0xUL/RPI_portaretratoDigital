(function () {
  "use strict";

  const POLL_INTERVAL_MS = 10_000;
  const WEATHER_INTERVAL_MS = 20 * 60_000;
  const DEFAULT_SLIDE_INTERVAL_MS = 15_000;

  const layerA = document.getElementById("layer-a");
  const layerB = document.getElementById("layer-b");
  const body = document.body;
  const overlayClock = document.getElementById("overlay-clock");
  const overlayDate = document.getElementById("overlay-date");
  const overlayWeather = document.getElementById("overlay-weather");
  const emptyState = document.getElementById("empty-state");
  const blackout = document.getElementById("blackout");

  let photos = [];
  let currentIndex = 0;
  let activeLayer = layerA;
  let inactiveLayer = layerB;

  let settings = {
    slideshow_interval_seconds: 15,
    slideshow_order: "sequential",
    transition_effects: ["fade"],
    image_fit: "cover",
    display_orientation: "landscape",
    show_clock: true,
    show_date: true,
    show_weather: false,
  };

  const TRANSITION_CLASSES = [
    "transition-none",
    "transition-fade",
    "transition-slide",
    "transition-slide-up",
    "transition-zoom-in",
    "transition-zoom-out",
    "transition-blur",
  ];

  function pickTransition() {
    const list =
      settings.transition_effects && settings.transition_effects.length
        ? settings.transition_effects
        : ["fade"];
    return list[Math.floor(Math.random() * list.length)];
  }

  let lastPhotosVersion = null;
  let lastSettingsVersion = null;
  let mainTimer = null;

  function applySettingsToDom() {
    body.classList.toggle("fit-cover", settings.image_fit === "cover");
    body.classList.toggle("fit-contain", settings.image_fit === "contain");
    body.classList.toggle("orientation-landscape", settings.display_orientation === "landscape");
    body.classList.toggle("orientation-portrait", settings.display_orientation === "portrait");

    overlayClock.classList.toggle("hidden", !settings.show_clock);
    overlayDate.classList.toggle("hidden", !settings.show_date);
    overlayWeather.classList.toggle("hidden", !settings.show_weather);
  }

  function nextIndex() {
    if (photos.length <= 1) return 0;
    if (settings.slideshow_order === "random") {
      let idx;
      do {
        idx = Math.floor(Math.random() * photos.length);
      } while (idx === currentIndex);
      return idx;
    }
    return (currentIndex + 1) % photos.length;
  }

  function showPhoto(index, { immediate } = {}) {
    if (!photos.length) return;
    const photo = photos[index];
    const img = new Image();
    img.onload = () => {
      inactiveLayer.src = photo.display_url;
      if (immediate) {
        activeLayer.src = photo.display_url;
        activeLayer.classList.add("active");
        inactiveLayer.classList.remove("active");
        return;
      }
      body.classList.remove(...TRANSITION_CLASSES);
      body.classList.add("transition-" + pickTransition());
      requestAnimationFrame(() => {
        inactiveLayer.classList.add("active");
        activeLayer.classList.remove("active");
        const tmp = activeLayer;
        activeLayer = inactiveLayer;
        inactiveLayer = tmp;
      });
    };
    img.src = photo.display_url;
  }

  function advanceSlide() {
    if (!photos.length) return;
    currentIndex = nextIndex();
    showPhoto(currentIndex);
  }

  function restartMainTimer() {
    if (mainTimer) clearInterval(mainTimer);
    const ms = Math.max(3, settings.slideshow_interval_seconds) * 1000 || DEFAULT_SLIDE_INTERVAL_MS;
    mainTimer = setInterval(advanceSlide, ms);
  }

  function reconcilePhotos(newPhotos) {
    const currentId = photos[currentIndex] ? photos[currentIndex].id : null;
    photos = newPhotos;
    emptyState.classList.toggle("hidden", photos.length > 0);
    if (!photos.length) return;

    const keepIndex = photos.findIndex((p) => p.id === currentId);
    currentIndex = keepIndex >= 0 ? keepIndex : 0;
    showPhoto(currentIndex, { immediate: true });
  }

  async function poll() {
    let state;
    try {
      const res = await fetch("/api/display/state", { cache: "no-store" });
      if (!res.ok) return;
      state = await res.json();
    } catch (err) {
      return;
    }

    if (state.settings_version !== lastSettingsVersion) {
      const intervalChanged =
        settings.slideshow_interval_seconds !== state.settings.slideshow_interval_seconds;
      settings = state.settings;
      lastSettingsVersion = state.settings_version;
      applySettingsToDom();
      if (intervalChanged || !mainTimer) restartMainTimer();
    }

    if (state.photos_version !== lastPhotosVersion) {
      lastPhotosVersion = state.photos_version;
      reconcilePhotos(state.photos);
    }

    blackout.classList.toggle("visible", !state.screen_on);
  }

  function updateClock() {
    const now = new Date();
    overlayClock.textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    overlayDate.textContent = now.toLocaleDateString([], {
      weekday: "long",
      day: "numeric",
      month: "long",
    });
  }

  async function updateWeather() {
    if (!settings.show_weather) return;
    try {
      const res = await fetch("/api/display/weather", { cache: "no-store" });
      if (res.status === 204) {
        overlayWeather.textContent = "";
        return;
      }
      if (!res.ok) return;
      const data = await res.json();
      if (data.temperature === null || data.temperature === undefined) return;
      const unit = data.units === "imperial" ? "°F" : "°C";
      overlayWeather.textContent = `${Math.round(data.temperature)}${unit}`;
    } catch (err) {
      // silencioso: mantiene el último valor mostrado
    }
  }

  // --- Menú de apagado: 3 toques en la esquina superior izquierda ---
  const TAP_COUNT = 3;
  const TAP_WINDOW_MS = 1500;
  const MENU_AUTO_DISMISS_MS = 10_000;

  const tapZone = document.getElementById("tap-zone");
  const powerMenu = document.getElementById("power-menu");
  let tapTimes = [];
  let menuDismissTimer = null;

  function openPowerMenu() {
    powerMenu.classList.remove("hidden");
    if (menuDismissTimer) clearTimeout(menuDismissTimer);
    menuDismissTimer = setTimeout(closePowerMenu, MENU_AUTO_DISMISS_MS);
  }

  function closePowerMenu() {
    powerMenu.classList.add("hidden");
    if (menuDismissTimer) clearTimeout(menuDismissTimer);
  }

  async function sendPowerAction(action, extra) {
    try {
      await fetch("/api/display/power-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...extra }),
      });
    } catch (err) {
      // silencioso: si falla, el usuario puede reintentar tocando de nuevo
    }
  }

  tapZone.addEventListener("click", () => {
    const now = Date.now();
    tapTimes = tapTimes.filter((t) => now - t < TAP_WINDOW_MS);
    tapTimes.push(now);
    if (tapTimes.length >= TAP_COUNT) {
      tapTimes = [];
      openPowerMenu();
    }
  });

  document.getElementById("power-hide").addEventListener("click", () => {
    sendPowerAction("hide", { hide_seconds: 120 });
    closePowerMenu();
  });

  document.getElementById("power-reboot").addEventListener("click", () => {
    sendPowerAction("reboot", {});
    powerMenu.querySelector(".power-menu-box").innerHTML = "<p>Reiniciando…</p>";
  });

  document.getElementById("power-shutdown").addEventListener("click", () => {
    sendPowerAction("shutdown", {});
    powerMenu.querySelector(".power-menu-box").innerHTML =
      "<p>Apagando… esperá unos segundos antes de desconectar la Pi.</p>";
  });

  document.getElementById("power-cancel").addEventListener("click", closePowerMenu);

  applySettingsToDom();
  restartMainTimer();
  poll();
  updateClock();
  updateWeather();

  setInterval(poll, POLL_INTERVAL_MS);
  setInterval(updateClock, 1000);
  setInterval(updateWeather, WEATHER_INTERVAL_MS);
})();
