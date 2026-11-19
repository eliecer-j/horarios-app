(function () {
  "use strict";

  const numberFormatter = new Intl.NumberFormat("es-CO", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  let anchor = null;
  let currentRange = null;
  let dragging = false;
  let dragPoint = null;
  let scrollFrame = null;
  let pendingScroll = null;

  function activeDialog() {
    const dialog = document.getElementById("analysis-detail-dialog");
    return dialog && dialog.open ? dialog : null;
  }

  function coordinateOf(cell) {
    const row = cell.parentElement;
    const body = row && row.parentElement;
    if (!body || body.tagName !== "TBODY") return null;
    return {
      row: Array.prototype.indexOf.call(body.rows, row),
      col: cell.cellIndex,
    };
  }

  function cellAt(table, row, col) {
    const body = table.tBodies[0];
    if (!body) return null;
    const tableRow = body.rows[row];
    return tableRow ? tableRow.cells[col] || null : null;
  }

  function cellsInRange(table, range) {
    const cells = [];
    const body = table.tBodies[0];
    if (!body) return cells;
    for (let row = range.r1; row <= range.r2; row += 1) {
      for (let col = range.c1; col <= range.c2; col += 1) {
        const cell = cellAt(table, row, col);
        if (cell) cells.push(cell);
      }
    }
    return cells;
  }

  function clearHighlight(table) {
    table
      .querySelectorAll(".is-range, .is-anchor, .is-end")
      .forEach(function (cell) {
        cell.classList.remove("is-range", "is-anchor", "is-end");
      });
    table.classList.remove("is-selecting");
  }

  function updateStatus(table, range) {
    const dialog = table.closest("dialog");
    if (!dialog) return;
    const metrics = dialog.querySelector("[data-analysis-metrics]");
    const hint = dialog.querySelector("[data-analysis-hint]");
    const actions = dialog.querySelector("[data-analysis-actions]");
    if (!metrics) return;

    const cells = cellsInRange(table, range);
    const values = [];
    cells.forEach(function (cell) {
      if (cell.dataset.value === undefined) return;
      const value = Number(cell.dataset.value);
      if (Number.isFinite(value)) values.push(value);
    });

    function setMetric(name, text) {
      const target = dialog.querySelector('[data-metric="' + name + '"]');
      if (target) target.textContent = text;
    }

    if (values.length) {
      const sum = values.reduce(function (total, value) {
        return total + value;
      }, 0);
      setMetric("sum", numberFormatter.format(sum));
      setMetric("avg", numberFormatter.format(sum / values.length));
      setMetric("min", numberFormatter.format(Math.min.apply(null, values)));
      setMetric("max", numberFormatter.format(Math.max.apply(null, values)));
    } else {
      setMetric("sum", "—");
      setMetric("avg", "—");
      setMetric("min", "—");
      setMetric("max", "—");
    }
    setMetric("count", String(cells.length));

    metrics.hidden = false;
    if (hint) hint.hidden = true;
    if (actions) actions.hidden = false;
  }

  function setSelection(table, start, end) {
    clearHighlight(table);
    const range = {
      r1: Math.min(start.row, end.row),
      r2: Math.max(start.row, end.row),
      c1: Math.min(start.col, end.col),
      c2: Math.max(start.col, end.col),
    };
    cellsInRange(table, range).forEach(function (cell) {
      cell.classList.add("is-range");
    });
    const startCell = cellAt(table, start.row, start.col);
    if (startCell) startCell.classList.add("is-anchor");
    const endCell = cellAt(table, end.row, end.col);
    if (endCell) endCell.classList.add("is-end");

    currentRange = { table: table, range: range };
    updateStatus(table, range);
  }

  function resetStatus(dialog) {
    if (!dialog) return;
    const metrics = dialog.querySelector("[data-analysis-metrics]");
    const hint = dialog.querySelector("[data-analysis-hint]");
    const actions = dialog.querySelector("[data-analysis-actions]");
    if (metrics) metrics.hidden = true;
    if (hint) hint.hidden = false;
    if (actions) actions.hidden = true;
  }

  function resetSelection() {
    anchor = null;
    currentRange = null;
    dragging = false;
    dragPoint = null;
    stopScrollLoop();
    document.querySelectorAll("table.analysis-detail-table").forEach(clearHighlight);
  }

  function cellUnderPoint(x, y) {
    const element = document.elementFromPoint(x, y);
    if (!element || !element.closest) return null;
    const cell = element.closest("td, th");
    if (!cell || !cell.closest("tbody")) return null;
    return cell;
  }

  function nearestCell(table, x, y) {
    const body = table.tBodies[0];
    if (!body || !body.rows.length) return null;
    const rows = body.rows;
    let rowIndex = 0;
    for (let index = 0; index < rows.length; index += 1) {
      const rect = rows[index].getBoundingClientRect();
      if (y >= rect.top && y <= rect.bottom) {
        rowIndex = index;
        break;
      }
      if (y > rect.bottom) rowIndex = index;
      if (y < rect.top) {
        rowIndex = Math.max(0, index - 1);
        break;
      }
    }
    const row = rows[rowIndex];
    if (!row || !row.cells.length) return null;
    let cellIndex = 0;
    for (let index = 0; index < row.cells.length; index += 1) {
      const rect = row.cells[index].getBoundingClientRect();
      if (x >= rect.left && x <= rect.right) {
        cellIndex = index;
        break;
      }
      if (x > rect.right) cellIndex = index;
      if (x < rect.left) {
        cellIndex = Math.max(0, index - 1);
        break;
      }
    }
    return row.cells[cellIndex];
  }

  function updateSelectionFromPoint() {
    if (!dragging || !dragPoint || !anchor || !currentRange) return;
    const table = currentRange.table;
    const cell =
      cellUnderPoint(dragPoint.x, dragPoint.y) ||
      nearestCell(table, dragPoint.x, dragPoint.y);
    if (!cell || !table.contains(cell)) return;
    const coordinate = coordinateOf(cell);
    if (coordinate) setSelection(table, anchor, coordinate);
  }

  function scrollTowardsPointer() {
    if (!dragging || !dragPoint || !currentRange) return false;
    const container = currentRange.table.closest(".analysis-detail-scroll");
    if (!container) return false;
    const rect = container.getBoundingClientRect();
    const edge = 30;
    let deltaX = 0;
    let deltaY = 0;
    if (dragPoint.x < rect.left + edge) {
      deltaX = dragPoint.x - (rect.left + edge);
    } else if (dragPoint.x > rect.right - edge) {
      deltaX = dragPoint.x - (rect.right - edge);
    }
    if (dragPoint.y < rect.top + edge) {
      deltaY = dragPoint.y - (rect.top + edge);
    } else if (dragPoint.y > rect.bottom - edge) {
      deltaY = dragPoint.y - (rect.bottom - edge);
    }
    if (!deltaX && !deltaY) return false;
    const beforeTop = container.scrollTop;
    const beforeLeft = container.scrollLeft;
    container.scrollTop += Math.max(-26, Math.min(26, deltaY * 0.9));
    container.scrollLeft += Math.max(-26, Math.min(26, deltaX * 0.9));
    if (container.scrollTop === beforeTop && container.scrollLeft === beforeLeft) {
      return false;
    }
    updateSelectionFromPoint();
    return true;
  }

  function stepScroll() {
    scrollFrame = null;
    if (!dragging) return;
    scrollTowardsPointer();
    scrollFrame = window.requestAnimationFrame(stepScroll);
  }

  function startScrollLoop() {
    if (scrollFrame === null) {
      scrollFrame = window.requestAnimationFrame(stepScroll);
    }
  }

  function stopScrollLoop() {
    if (scrollFrame !== null) {
      window.cancelAnimationFrame(scrollFrame);
      scrollFrame = null;
    }
  }

  function selectionText() {
    if (!currentRange) return "";
    const body = currentRange.table.tBodies[0];
    if (!body) return "";
    const range = currentRange.range;
    const lines = [];
    for (let row = range.r1; row <= range.r2; row += 1) {
      const tableRow = body.rows[row];
      if (!tableRow) continue;
      const values = [];
      for (let col = range.c1; col <= range.c2; col += 1) {
        const cell = tableRow.cells[col];
        values.push(
          cell ? cell.innerText.replace(/\s+/g, " ").trim() : ""
        );
      }
      lines.push(values.join("\t"));
    }
    return lines.join("\n");
  }

  function textareaCopy(text) {
    const dialog = document.querySelector("dialog[open]");
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.className = "analysis-detail-clipboard";
    // En un <dialog> modal el resto del documento queda inerte: el textarea
    // debe vivir dentro del diálogo para que el copiado funcione por HTTP.
    (dialog || document.body).appendChild(area);
    area.focus();
    area.select();
    area.setSelectionRange(0, area.value.length);
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }
    area.remove();
    return copied;
  }

  function legacyCopy(text) {
    let copied = false;
    function onCopy(event) {
      if (!event.clipboardData) return;
      event.clipboardData.setData("text/plain", text);
      event.preventDefault();
      copied = true;
    }
    document.addEventListener("copy", onCopy, true);
    try {
      document.execCommand("copy");
    } catch (error) {
      copied = false;
    } finally {
      document.removeEventListener("copy", onCopy, true);
    }
    return copied || textareaCopy(text);
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        return navigator.clipboard.writeText(text).then(
          function () {
            return true;
          },
          function () {
            return legacyCopy(text);
          }
        );
      } catch (error) {
        return Promise.resolve(legacyCopy(text));
      }
    }
    return Promise.resolve(legacyCopy(text));
  }

  function flash(button, copied) {
    if (!button) return;
    if (button.dataset.originalLabel === undefined) {
      button.dataset.originalLabel = button.textContent;
    }
    button.textContent = copied ? "Copiado" : "No se pudo copiar";
    window.setTimeout(function () {
      button.textContent = button.dataset.originalLabel;
    }, 1600);
  }

  function copySelection(button) {
    const text = selectionText();
    if (!text) return;
    copyText(text).then(function (copied) {
      flash(button, copied);
    });
  }

  document.addEventListener("pointerdown", function (event) {
    if (event.button !== 0) return;
    const dialog = activeDialog();
    if (!dialog || !dialog.contains(event.target)) return;
    if (event.target.closest("button, a, input, select, textarea, [contenteditable]")) {
      return;
    }
    const cell = event.target.closest("td, th");
    if (!cell || !cell.closest("tbody")) return;
    const table = cell.closest("table.analysis-detail-table");
    if (!table) return;
    const coordinate = coordinateOf(cell);
    if (!coordinate) return;

    if (event.pointerType !== "touch") event.preventDefault();
    if (event.shiftKey && anchor && currentRange && currentRange.table === table) {
      setSelection(table, anchor, coordinate);
    } else {
      anchor = coordinate;
      setSelection(table, anchor, coordinate);
    }
    if (event.pointerType !== "touch") {
      dragging = true;
      dragPoint = { x: event.clientX, y: event.clientY };
      table.classList.add("is-selecting");
    }
  });

  document.addEventListener("pointermove", function (event) {
    if (!dragging) return;
    dragPoint = { x: event.clientX, y: event.clientY };
    scrollTowardsPointer();
    updateSelectionFromPoint();
    startScrollLoop();
  });

  function endDrag() {
    if (!dragging) return;
    dragging = false;
    dragPoint = null;
    stopScrollLoop();
    document
      .querySelectorAll("table.analysis-detail-table.is-selecting")
      .forEach(function (table) {
        table.classList.remove("is-selecting");
      });
  }

  document.addEventListener("pointerup", endDrag);
  document.addEventListener("pointercancel", endDrag);
  window.addEventListener("blur", endDrag);

  document.addEventListener("keydown", function (event) {
    if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "c") {
      return;
    }
    const dialog = activeDialog();
    if (!dialog || !currentRange) return;
    const active = document.activeElement;
    if (
      active &&
      active.closest &&
      active.closest("input, textarea, select, [contenteditable]")
    ) {
      return;
    }
    const selection = window.getSelection();
    if (selection && !selection.isCollapsed && selection.toString()) return;
    event.preventDefault();
    copySelection(dialog.querySelector("[data-analysis-copy]"));
  });

  document.addEventListener("click", function (event) {
    const clearButton = event.target.closest("[data-analysis-clear]");
    if (clearButton) {
      const dialog = clearButton.closest("dialog");
      resetSelection();
      resetStatus(dialog);
      return;
    }
    const copyButton = event.target.closest("[data-analysis-copy]");
    if (copyButton) copySelection(copyButton);
  });

  document.addEventListener(
    "close",
    function (event) {
      if (event.target && event.target.id === "analysis-detail-dialog") {
        resetSelection();
      }
    },
    true
  );

  function rememberRefreshScroll(event) {
    const source = event.detail && event.detail.elt;
    if (!source || !source.closest || !source.closest(".analysis-detail-refresh")) {
      return;
    }
    const container = document.querySelector(
      "#analysis-detail-dialog .analysis-detail-scroll"
    );
    pendingScroll = container
      ? { top: container.scrollTop, left: container.scrollLeft }
      : null;
  }

  function restoreRefreshScroll() {
    if (!pendingScroll) return;
    const container = document.querySelector(
      "#analysis-detail-dialog .analysis-detail-scroll"
    );
    if (container) {
      container.scrollTop = pendingScroll.top;
      container.scrollLeft = pendingScroll.left;
    }
    pendingScroll = null;
  }

  document.body.addEventListener("htmx:beforeRequest", rememberRefreshScroll);
  document.body.addEventListener("htmx:afterSettle", restoreRefreshScroll);
  document.body.addEventListener("htmx:beforeSwap", resetSelection);
  document.body.addEventListener("htmx:afterSettle", resetSelection);
})();
