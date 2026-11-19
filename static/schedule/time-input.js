(function () {
  "use strict";

  // Convierte lo que se escribe con el teclado numérico a HH:MM.
  // Acepta 12.30, 12,30, 12:30, 930 y 1230.
  function formatValue(raw) {
    const value = String(raw || "");
    const separated = value.match(/^\s*(\d{0,2})\s*[.:,]\s*(\d{0,2})/);
    if (separated) {
      const hour = separated[1];
      const minute = separated[2];
      if (!hour) return "";
      return hour.padStart(2, "0") + ":" + minute;
    }
    let digits = value.replace(/\D/g, "").slice(0, 4);
    if (!digits) return "";
    if (digits.length === 1 && digits[0] >= "3") digits = "0" + digits;
    if (digits.length <= 2) return digits;
    return digits.slice(0, 2) + ":" + digits.slice(2);
  }

  function completeValue(raw) {
    const value = formatValue(raw);
    if (/^\d{1,2}$/.test(value)) return value.padStart(2, "0");
    if (/^\d{2}:\d$/.test(value)) return value + "0";
    return value;
  }

  document.body.addEventListener("input", function (event) {
    const input = event.target.closest("input[data-time-input]");
    if (!input) return;
    const next = formatValue(input.value);
    if (input.value !== next) {
      input.value = next;
      input.setSelectionRange(next.length, next.length);
    }
  });

  document.body.addEventListener("blur", function (event) {
    const input = event.target.closest("input[data-time-input]");
    if (!input) return;
    const next = completeValue(input.value);
    if (input.value !== next) input.value = next;
  }, true);
})();