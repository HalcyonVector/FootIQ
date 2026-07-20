/**
 * FootIQ — generic custom-select upgrade. Wraps a native <select> in a
 * translucent glass dropdown UI while keeping the <select> itself in the
 * DOM (hidden, not removed) as the source of truth, so any existing code
 * that reads `.value` or listens for `change` on these elements keeps
 * working completely unchanged. Only what the OPENED menu looks like
 * changes — a native <select>'s option list is OS-rendered and can't be
 * styled to match the app's glass aesthetic at all, which was the actual
 * limitation this works around.
 *
 * Call upgradeSelects() again after anything dynamically repopulates a
 * <select>'s options (e.g. Explore's category -> metric list) or replaces
 * a select's outer HTML (e.g. Compare's renderSlots()) — it's idempotent
 * and safe to call as often as needed.
 */

function _buildCustomSelect(selectEl) {
  selectEl.dataset.csUpgraded = "1";
  selectEl.classList.add("cs-native");

  const wrap = document.createElement("div");
  wrap.className = "custom-select";
  selectEl.parentNode.insertBefore(wrap, selectEl);

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "custom-select-btn";
  const labelSpan = document.createElement("span");
  labelSpan.className = "custom-select-label";
  const arrow = document.createElement("span");
  arrow.className = "dd-arrow";
  arrow.textContent = "▾";
  btn.appendChild(labelSpan);
  btn.appendChild(arrow);

  const menu = document.createElement("div");
  menu.className = "custom-select-menu";

  wrap.appendChild(selectEl);
  wrap.appendChild(btn);
  wrap.appendChild(menu);

  function render() {
    const selOpt = selectEl.options[selectEl.selectedIndex];
    labelSpan.textContent = selOpt ? selOpt.text : "";
    menu.innerHTML = "";
    [...selectEl.options].forEach((opt, i) => {
      const item = document.createElement("div");
      item.className = "custom-select-item" + (i === selectEl.selectedIndex ? " active" : "");
      item.textContent = opt.text;
      item.addEventListener("click", () => {
        if (selectEl.selectedIndex !== i) {
          selectEl.selectedIndex = i;
          selectEl.dispatchEvent(new Event("change", { bubbles: true }));
        }
        wrap.classList.remove("open");
      });
      menu.appendChild(item);
    });
  }

  btn.addEventListener("click", e => {
    e.stopPropagation();
    const willOpen = !wrap.classList.contains("open");
    document.querySelectorAll(".custom-select.open").forEach(w => w.classList.remove("open"));
    if (willOpen) { _positionMenu(wrap, btn); wrap.classList.add("open"); _kbSetActive(menu, selectEl.selectedIndex); }
  });
  menu.addEventListener("click", e => e.stopPropagation());
  selectEl.addEventListener("change", render);

  // ── Keyboard nav: the native <select> this replaces already supported
  // arrow keys, Enter, Escape, Home/End for free — a plain clickable div
  // doesn't, so that's rebuilt here rather than just left worse than before.
  btn.addEventListener("keydown", e => {
    const items = [...menu.children];
    if (!items.length) return;
    const isOpen = wrap.classList.contains("open");

    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!isOpen) {
        document.querySelectorAll(".custom-select.open").forEach(w => w.classList.remove("open"));
        _positionMenu(wrap, btn);
        wrap.classList.add("open");
        _kbSetActive(menu, selectEl.selectedIndex);
        return;
      }
      const cur = items.findIndex(i => i.classList.contains("kb-active"));
      const next = e.key === "ArrowDown"
        ? Math.min((cur === -1 ? selectEl.selectedIndex : cur) + 1, items.length - 1)
        : Math.max((cur === -1 ? selectEl.selectedIndex : cur) - 1, 0);
      _kbSetActive(menu, next);
    } else if (e.key === "Home" && isOpen) {
      e.preventDefault();
      _kbSetActive(menu, 0);
    } else if (e.key === "End" && isOpen) {
      e.preventDefault();
      _kbSetActive(menu, items.length - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      if (isOpen) {
        e.preventDefault();
        const active = items.findIndex(i => i.classList.contains("kb-active"));
        if (active !== -1) items[active].click();
      }
      // else: let the native click-on-Enter/Space open it, handled by the button itself.
    } else if (e.key === "Escape" && isOpen) {
      e.preventDefault();
      wrap.classList.remove("open");
    }
  });

  wrap._csRender = render;
  render();
}

// Opens downward by default, but flips above the button when there isn't
// enough room below (e.g. a dropdown near the bottom of a short page) —
// otherwise the menu just spills past the viewport/footer instead of
// clipping or scrolling into view.
function _positionMenu(wrap, btn) {
  const rect = btn.getBoundingClientRect();
  const menuMaxHeight = 260; // matches .custom-select-menu's max-height
  const spaceBelow = window.innerHeight - rect.bottom;
  const spaceAbove = rect.top;
  const dropUp = spaceBelow < menuMaxHeight + 12 && spaceAbove > spaceBelow;
  wrap.classList.toggle("drop-up", dropUp);
}

function _kbSetActive(menu, idx) {
  [...menu.children].forEach((item, i) => item.classList.toggle("kb-active", i === idx));
  const target = menu.children[idx];
  if (target) target.scrollIntoView({ block: "nearest" });
}

function upgradeSelects(root = document) {
  root.querySelectorAll(
    "select.filter-select:not([data-cs-upgraded]), select.slot-season-sel:not([data-cs-upgraded])"
  ).forEach(_buildCustomSelect);

  // Re-sync labels/menus for already-upgraded selects whose OPTIONS may
  // have just changed underneath them (e.g. Explore's metric list).
  root.querySelectorAll("select.cs-native[data-cs-upgraded]").forEach(sel => {
    const wrap = sel.closest(".custom-select");
    if (wrap && wrap._csRender) wrap._csRender();
  });
}

document.addEventListener("click", () => {
  document.querySelectorAll(".custom-select.open").forEach(w => w.classList.remove("open"));
});

document.addEventListener("DOMContentLoaded", () => upgradeSelects());
