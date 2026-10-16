/*
 * Behaviour tests for the keyboard navigation on "گزارش کارکرد هر نازل".
 *
 * Usage: node nozzle_ledger_keyboard.js <rendered-page.html> <rendered-empty-page.html>
 * Needs the `jsdom` npm package (resolved via NODE_PATH). Prints one JSON
 * object {check name: true | false} -- run by test_nozzle_ledger_keyboard.py,
 * which skips itself when node/jsdom are not installed.
 *
 * The REAL rendered page (its real inline <script>) is loaded into jsdom and
 * driven with real KeyboardEvents. jsdom has no layout engine, so layout is
 * modelled: 600px viewport, rows 30px tall, table starting 200px down, and
 * scrollIntoView({block:'nearest'}) implemented with the spec's semantics
 * (scroll only as far as needed, honouring the row's scroll-margin of 40px).
 */
const fs = require('fs');
const { JSDOM } = require('jsdom');

const VIEWPORT = 600, ROW_H = 30, TABLE_TOP = 200, MARGIN = 40;

function load(file) {
  const html = fs.readFileSync(file, 'utf8');
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    beforeParse(window) {
      window.JalaliCalendar = { bindNavInputs() {}, mount() {}, init() {} };   // unrelated calendar widget, stubbed
      window.__scrollY = 0;
      window.__scrollCalls = [];
      Object.defineProperty(window, 'innerHeight', { value: VIEWPORT });
      Object.defineProperty(window, 'scrollY', { get: () => window.__scrollY });
      const proto = window.Element.prototype;
      const rowIndex = (el) => Array.prototype.indexOf.call(el.parentNode.children, el);
      proto.getBoundingClientRect = function () {
        if (this.tagName === 'TR' && this.parentNode.tagName === 'TBODY') {
          const top = TABLE_TOP + rowIndex(this) * ROW_H - window.__scrollY;
          return { top, bottom: top + ROW_H, height: ROW_H, left: 0, right: 0, width: 0 };
        }
        return { top: 0, bottom: 0, height: 0, left: 0, right: 0, width: 0 };
      };
      proto.scrollIntoView = function (opts) {
        window.__scrollCalls.push({ index: this.tagName === 'TR' ? rowIndex(this) : -1, opts });
        if (this.tagName !== 'TR') return;
        const top = this.getBoundingClientRect().top;
        const bottom = top + ROW_H;
        if (top - MARGIN < 0) window.__scrollY += top - MARGIN;                    // scroll up
        else if (bottom + MARGIN > VIEWPORT) window.__scrollY += bottom + MARGIN - VIEWPORT; // scroll down
        if (window.__scrollY < 0) window.__scrollY = 0;
      };
    },
  });
  const { window } = dom;
  const select = window.document.getElementById('nozzle-select');
  const changes = [];
  if (select) {
    select.removeAttribute('onchange');        // jsdom cannot navigate; record instead
    select.addEventListener('change', () => changes.push(select.value));
  }
  return { window, doc: window.document, select, changes };
}

function key(page, k, target, extra) {
  const ev = new page.window.KeyboardEvent('keydown', Object.assign(
    { key: k, bubbles: true, cancelable: true }, extra || {}));
  (target || page.doc.body).dispatchEvent(ev);
  return ev.defaultPrevented;
}

const selectedRows = (p) => Array.from(p.doc.querySelectorAll('#nozzle-ledger-table tbody tr.row-selected'));
const selectedIndex = (p) => {
  const r = selectedRows(p);
  return r.length === 1 ? Array.prototype.indexOf.call(r[0].parentNode.children, r[0]) : r.length === 0 ? -1 : -99;
};
const hintVisible = (p) => !p.doc.getElementById('table-mode-hint').hidden;
const inViewport = (p) => {
  const i = selectedIndex(p);
  const row = p.doc.querySelectorAll('#nozzle-ledger-table tbody tr')[i];
  if (!row) return false;
  const r = row.getBoundingClientRect();
  return r.top >= 0 && r.bottom <= VIEWPORT;
};

const out = {};
const check = (name, ok) => { out[name] = !!ok; };

// ------------------------------------------------------------------ page with rows
try {
  const p = load(process.argv[2]);
  const rows = p.doc.querySelectorAll('#nozzle-ledger-table tbody tr').length;
  const options = Array.from(p.select.options).filter((o) => o.value);
  const startValue = p.select.value;
  check('fixture: page has many rows (>= 30) and 26 nozzles', rows >= 30 && options.length === 26);

  // ---- Mode 1 (default): nozzle navigation, unchanged
  const idx = options.findIndex((o) => o.value === startValue);
  let prevented = key(p, 'ArrowUp');
  check('mode1: ArrowUp selects the next nozzle', p.select.value === options[idx + 1].value && prevented);
  key(p, 'ArrowDown');
  check('mode1: ArrowDown selects the previous nozzle', p.select.value === startValue);
  check('mode1: each arrow fired exactly one change event', p.changes.length === 2);
  check('mode1: no table row is highlighted by default', selectedRows(p).length === 0 && !hintVisible(p));

  // boundaries of nozzle navigation
  p.select.value = options[options.length - 1].value;
  p.changes.length = 0;
  prevented = key(p, 'ArrowUp');
  check('mode1: ArrowUp on the last nozzle does nothing', p.changes.length === 0 && !prevented);
  p.select.value = options[0].value;
  prevented = key(p, 'ArrowDown');
  check('mode1: ArrowDown on the first nozzle does nothing', p.changes.length === 0 && !prevented);
  p.select.value = startValue;
  p.changes.length = 0;

  // ---- Enter -> Mode 2
  prevented = key(p, 'Enter');
  check('enter: switches to table mode and highlights the FIRST row', selectedIndex(p) === 0);
  check('enter: Enter itself was consumed (no default action)', prevented);
  check('enter: mode hint is shown', hintVisible(p));
  check('enter: nozzle selection untouched', p.select.value === startValue && p.changes.length === 0);
  check('enter: highlighted row exposes aria-selected', selectedRows(p)[0].getAttribute('aria-selected') === 'true');

  // ---- Mode 2: row navigation
  prevented = key(p, 'ArrowDown');
  check('mode2: ArrowDown moves to the next row', selectedIndex(p) === 1 && prevented);
  key(p, 'ArrowDown'); key(p, 'ArrowDown');
  check('mode2: three downs from row 0 -> row 3', selectedIndex(p) === 3);
  key(p, 'ArrowUp');
  check('mode2: ArrowUp moves to the previous row', selectedIndex(p) === 2);
  check('mode2: arrows never change the nozzle', p.changes.length === 0 && p.select.value === startValue);
  check('mode2: only one row is ever highlighted', selectedRows(p).length === 1);

  // first-row boundary
  key(p, 'ArrowUp'); key(p, 'ArrowUp'); key(p, 'ArrowUp'); key(p, 'ArrowUp'); key(p, 'ArrowUp');
  check('mode2: cannot move above the first row', selectedIndex(p) === 0);
  prevented = key(p, 'ArrowUp');
  check('mode2: ArrowUp on first row stays put (page does not scroll natively)', selectedIndex(p) === 0 && prevented);

  // ---- automatic scrolling while walking the whole table downwards
  let allVisible = true, scrolled = false;
  const y0 = p.window.__scrollY;
  for (let i = 1; i < rows; i++) {
    key(p, 'ArrowDown');
    if (selectedIndex(p) !== i) allVisible = false;
    if (!inViewport(p)) allVisible = false;
  }
  scrolled = p.window.__scrollY > y0;
  check('scroll: selected row stays inside the viewport on every step down', allVisible);
  check('scroll: the page really scrolled to follow the selection', scrolled);
  check('scroll: scrolling was requested with block "nearest" on the selected row',
    p.window.__scrollCalls.length > 0 &&
    p.window.__scrollCalls.every((c) => c.opts && c.opts.block === 'nearest') &&
    p.window.__scrollCalls[p.window.__scrollCalls.length - 1].index === rows - 1);

  // last-row boundary
  prevented = key(p, 'ArrowDown');
  check('mode2: cannot move below the last row', selectedIndex(p) === rows - 1 && prevented);

  // walk back up: still visible, scrolls back
  const yBottom = p.window.__scrollY;
  allVisible = true;
  for (let i = rows - 2; i >= 0; i--) {
    key(p, 'ArrowUp');
    if (selectedIndex(p) !== i || !inViewport(p)) allVisible = false;
  }
  check('scroll: selected row stays inside the viewport on every step up', allVisible);
  check('scroll: the page scrolled back up', p.window.__scrollY < yBottom);

  // ---- Enter again -> back to Mode 1
  key(p, 'ArrowDown'); key(p, 'ArrowDown');
  prevented = key(p, 'Enter');
  check('exit: second Enter removes the blue highlight', selectedRows(p).length === 0);
  check('exit: second Enter hides the mode hint and is consumed', !hintVisible(p) && prevented);
  p.changes.length = 0;
  key(p, 'ArrowUp');
  check('exit: ArrowUp navigates nozzles again', p.changes.length === 1 && p.select.value === options[idx + 1].value);
  key(p, 'ArrowDown');
  check('exit: ArrowDown navigates nozzles again', p.select.value === startValue && p.changes.length === 2);
  check('exit: no row navigation leaks into nozzle mode', selectedRows(p).length === 0);

  // ---- re-enter starts again at the first row
  key(p, 'Enter');
  check('re-enter: highlight starts again at the first row', selectedIndex(p) === 0);
  key(p, 'Enter');

  // ---- must not interfere with controls / modifiers / other keys
  const doc = p.doc;
  const dateInput = doc.querySelector('input.jalali-date-input');
  const button = doc.createElement('button'); doc.body.appendChild(button);
  const link = doc.createElement('a'); link.href = '#x'; doc.body.appendChild(link);
  const textarea = doc.createElement('textarea'); doc.body.appendChild(textarea);
  const editable = doc.createElement('div'); editable.contentEditable = 'true';
  Object.defineProperty(editable, 'isContentEditable', { value: true });
  doc.body.appendChild(editable);
  let untouched = true;
  [[p.select, 'select'], [dateInput, 'input'], [button, 'button'], [link, 'link'], [textarea, 'textarea'], [editable, 'editable']]
    .forEach(([el, name]) => {
      ['Enter', 'ArrowUp', 'ArrowDown'].forEach((k) => {
        const before = p.changes.length;
        const pr = key(p, k, el);
        if (pr || selectedRows(p).length !== 0 || p.changes.length !== before) { untouched = false; out['ignored in ' + name + ' (' + k + ')'] = false; }
      });
    });
  check('controls: Enter/Arrow keys are ignored inside select, input, button, link, textarea, editable', untouched);

  const mods = [{ ctrlKey: true }, { altKey: true }, { metaKey: true }];
  let modsOk = true;
  mods.forEach((m) => { ['Enter', 'ArrowUp', 'ArrowDown'].forEach((k) => {
    const before = p.changes.length;
    if (key(p, k, null, m) || selectedRows(p).length || p.changes.length !== before) modsOk = false;
  }); });
  check('modifiers: Ctrl/Alt/Meta + Enter/Arrow are ignored', modsOk);

  const otherPrevented = ['Escape', 'Tab', 'ArrowLeft', 'ArrowRight', ' ', 'a', 'Backspace', 'F2']
    .map((k) => key(p, k)).some(Boolean);
  check('other keys: untouched (never prevented, no mode change)', !otherPrevented && selectedRows(p).length === 0);

  // holding Enter (auto-repeat) must not flicker the mode
  key(p, 'Enter');
  key(p, 'Enter', null, { repeat: true }); key(p, 'Enter', null, { repeat: true });
  check('repeat: auto-repeated Enter does not toggle the mode', selectedIndex(p) === 0);
  key(p, 'Enter');
  check('repeat: a real Enter still exits', selectedRows(p).length === 0);

  // Enter pressed inside a form control while in table mode does not leave it
  key(p, 'Enter');
  key(p, 'Enter', dateInput);
  check('controls: Enter inside an input does not leave table mode', selectedIndex(p) === 0);

} catch (err) { out['harness error (rows page): ' + err.message] = false; }

// ------------------------------------------------------------------ page without a table
try {
  const p = load(process.argv[3]);
  check('empty: page has no table rows', p.doc.querySelectorAll('#nozzle-ledger-table tbody tr').length === 0);
  const prevented = key(p, 'Enter');
  check('empty: Enter does nothing and is not consumed', !prevented && selectedRows(p).length === 0);
  const options = Array.from(p.select.options).filter((o) => o.value);
  const idx = options.findIndex((o) => o.selected);
  key(p, 'ArrowUp');
  check('empty: nozzle navigation still works', p.changes.length === 1 && p.select.value === options[idx + 1].value);

} catch (err) { out['harness error (empty page): ' + err.message] = false; }

process.stdout.write(JSON.stringify(out));
