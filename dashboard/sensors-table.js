// sensors-table.js
export async function loadAllSensorsTable(containerId, options = {}) {
  const container = typeof containerId === 'string' ? document.getElementById(containerId) : containerId;
  if (!container) throw new Error('all-sensors container not found');

  const html = await fetch('sensors-table.html').then(r => r.text());
  container.innerHTML = html;

  return new AllSensorsTable(container.querySelector('.all-data-root'), options);
}

export class AllSensorsTable {
  constructor(root, opt) {
    this.root = root;
    this.body = root.querySelector('.js-body');
    this.filterInput = root.querySelector('.js-filter');
    this.toggleHidden = root.querySelector('.js-toggle-hidden');
    this.togglePin = root.querySelector('.js-toggle-pin');
    this.toggleFreeze = root.querySelector('.js-toggle-freeze');
    this.copyJsonBtn = root.querySelector('.js-copy-json');
    this.copyCsvBtn = root.querySelector('.js-copy-csv');

    // options
    this.baseHidden = opt.baseHidden ?? ['lat','lon','gps_fix','timestamp','_path','millis','time','session_id'];
    this.importantOrder = opt.importantOrder ?? ['RPM','VSS_kmh','Gear','CLT_C','OilTemp_C','EOT_OUT','IAT_C','FuelPressure_bar','OilPressure_bar','Batt_V','TPS_percent','fuelPumpTemp','CEL_Error'];
    this.rules = opt.rules ?? {};
    this.localKey = opt.localKey ?? 'mf25_userHiddenKeys';
    this.lastSnapshot = null;
    this.lastValues = new Map();
    this.rowsCache = [];

    // persistent hidden keys
    this.userHidden = new Set(JSON.parse(localStorage.getItem(this.localKey) || '[]'));

    // events
    this.body.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-action]');
      if (!btn) return;
      const key = btn.getAttribute('data-key');
      const action = btn.getAttribute('data-action');
      if (!key) return;
      if (action === 'hide') this.userHidden.add(key);
      if (action === 'unhide') this.userHidden.delete(key);
      localStorage.setItem(this.localKey, JSON.stringify([...this.userHidden]));
      if (this.lastSnapshot) this.render(this.lastSnapshot);
    });

    this.filterInput.addEventListener('input', () => this.applyFilter());
    [this.toggleHidden, this.togglePin].forEach(el => el.addEventListener('change', () => {
      if (this.lastSnapshot) this.render(this.lastSnapshot);
    }));

    this.copyJsonBtn.addEventListener('click', async () => {
      if (!this.lastSnapshot) return;
      try {
        await navigator.clipboard.writeText(JSON.stringify(this.lastSnapshot, null, 2));
        this.flashBtn(this.copyJsonBtn, 'Copied!', 'Copy JSON');
      } catch {
        this.flashBtn(this.copyJsonBtn, 'Copy failed', 'Copy JSON', 1200);
      }
    });

    this.copyCsvBtn.addEventListener('click', async () => {
      const header = ['Parameter','Value'];
      const lines = [header.join(',')];
      this.rowsCache.forEach(r => {
        const esc = s => String(s).replace(/"/g,'""');
        lines.push([`"${esc(r.key)}"`,`"${esc(r.display)}"`].join(','));
      });
      try {
        await navigator.clipboard.writeText(lines.join('\n'));
        this.flashBtn(this.copyCsvBtn, 'Copied!', 'Copy CSV');
      } catch {
        this.flashBtn(this.copyCsvBtn, 'Copy failed', 'Copy CSV', 1200);
      }
    });
  }

  flashBtn(btn, temp, orig, ms=900){
    const old = btn.textContent; btn.textContent = temp;
    setTimeout(()=> btn.textContent = orig ?? old, ms);
  }

  classify(key, rawVal){
    const v = Number(rawVal);
    if (!isFinite(v)) return null;
    const rule = this.rules[key];
    if (typeof rule === 'function') return rule(v);
    if (/_C$/.test(key)) { if (v>=130) return 'crit'; if (v>=110) return 'warn'; }
    return null;
  }

  rowHtml(k, display, sev, isHidden){
    const btn = isHidden
      ? `<button class="unhide-btn" data-action="unhide" data-key="${k}" title="보이기">+</button>`
      : `<button class="hide-btn" data-action="hide" data-key="${k}" title="숨기기">−</button>`;
    return `<tr data-key="${k}" data-val="${String(display)}" class="${sev?sev:''}">
      <td>${btn}<span>${k}</span></td>
      <td class="value">${display}</td>
    </tr>`;
  }

  render(data){
    const showHidden = this.toggleHidden.checked;
    const pinImportant = this.togglePin.checked;

    const entries = [];
    for (const k in data){
      if (!Object.prototype.hasOwnProperty.call(data, k)) continue;

      const baseHidden = this.baseHidden.includes(k);
      const userHide = this.userHidden.has(k);
      const shouldHide = (!showHidden) && (baseHidden || userHide);
      if (shouldHide) continue;

      const raw = data[k];
      const sev = this.classify(k, raw);
      const isNum = typeof raw === 'number';
      const display = isNum && !Number.isInteger(raw) ? Number(raw.toFixed(3)) : raw;

      entries.push({ key:k, display, sev, isHidden:(baseHidden || userHide) });
    }

    if (pinImportant){
      const idx = k => { const i = this.importantOrder.indexOf(k); return i === -1 ? 999 : i; };
      entries.sort((a,b)=> idx(a.key) - idx(b.key) || a.key.localeCompare(b.key));
    } else {
      entries.sort((a,b)=> a.key.localeCompare(b.key));
    }

    let html = '';
    this.rowsCache.length = 0;
    entries.forEach(r => {
      html += this.rowHtml(r.key, r.display, r.sev, r.isHidden && this.toggleHidden.checked);
      this.rowsCache.push({key:r.key, display:r.display});
    });
    this.body.innerHTML = html;

    // pulse on value change
    [...this.body.querySelectorAll('tr')].forEach(tr => {
      const key = tr.getAttribute('data-key');
      const cell = tr.querySelector('.value');
      const rawStr = tr.getAttribute('data-val');
      const currentVal = isNaN(Number(rawStr)) ? rawStr : Number(rawStr);
      const had = this.lastValues.has(key);
      const prevVal = this.lastValues.get(key);
      const changed = had ? currentVal !== prevVal : false;
      if (changed){
        cell.classList.remove('pulse'); void cell.offsetWidth; cell.classList.add('pulse');
        cell.title = `prev: ${prevVal}`;
      }
      this.lastValues.set(key, currentVal);
    });

    // after render, re-apply filter
    this.applyFilter();
  }

  applyFilter(){
    const q = this.filterInput.value.trim().toLowerCase();
    const rows = this.body.querySelectorAll('tr');
    rows.forEach(r => {
      const k = r.children[0].innerText.toLowerCase();
      const d = r.children[1].innerText.toLowerCase();
      r.style.display = (k.includes(q) || d.includes(q)) ? '' : 'none';
    });
  }

  update(data){
    if (!data) return;
    if (!this.toggleFreeze.checked){
      this.lastSnapshot = data;
      this.render(data);
    }
  }
}
