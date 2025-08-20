export async function loadAllSensorsTable(containerId, options = {}) {
  const container = typeof containerId === 'string' ? document.getElementById(containerId) : containerId;
  if (!container) throw new Error('all-sensors container not found');

  // 외부 HTML 파일을 fetch하여 컨테이너에 삽입
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

    // 옵션 설정
    this.baseHidden = opt.baseHidden ?? [];
    this.importantOrder = opt.importantOrder ?? [];
    this.rules = opt.rules ?? {};
    this.localKey = opt.localKey ?? 'mf25_userHiddenKeys';
    
    this.lastSnapshot = null;
    this.isInitialized = false;

    // DOM 요소의 참조를 저장할 Map
    this.rows = new Map(); 

    // 로컬 스토리지에서 사용자가 숨긴 키 목록 불러오기
    this.userHidden = new Set(JSON.parse(localStorage.getItem(this.localKey) || '[]'));

    // 이벤트 리스너 연결
    this.attachEvents();
  }

  // 이벤트 리스너를 설정하는 함수
  attachEvents() {
    // 숨기기/보이기 버튼 클릭 이벤트 (이벤트 위임 사용)
    this.body.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-action]');
      if (!btn) return;
      const key = btn.getAttribute('data-key');
      if (!key) return;
      
      if (btn.getAttribute('data-action') === 'hide') this.userHidden.add(key);
      if (btn.getAttribute('data-action') === 'unhide') this.userHidden.delete(key);
      
      localStorage.setItem(this.localKey, JSON.stringify([...this.userHidden]));
      this.applyVisibility(); // DOM을 다시 그리지 않고, 숨김 상태만 즉시 적용
    });

    // 툴바 컨트롤 이벤트
    this.filterInput.addEventListener('input', () => this.applyFilter());
    this.toggleHidden.addEventListener('change', () => this.applyVisibility());
    this.togglePin.addEventListener('change', () => this.resortRows());

    // JSON 복사 버튼 이벤트
    this.copyJsonBtn.addEventListener('click', async () => {
      if (!this.lastSnapshot) return;
      try {
        await navigator.clipboard.writeText(JSON.stringify(this.lastSnapshot, null, 2));
        this.flashBtn(this.copyJsonBtn, 'Copied!', 'Copy JSON');
      } catch {
        this.flashBtn(this.copyJsonBtn, 'Copy failed', 'Copy JSON', 1200);
      }
    });

    // CSV 복사 버튼 이벤트
    this.copyCsvBtn.addEventListener('click', async () => {
      const header = ['Parameter', 'Value'];
      const lines = [header.join(',')];
      this.body.querySelectorAll('tr:not([hidden])').forEach(tr => {
          const key = tr.dataset.key;
          const value = this.rows.get(key)?.lastVal ?? '';
          const esc = s => `"${String(s).replace(/"/g, '""')}"`;
          lines.push([esc(key), esc(value)].join(','));
      });
      try {
        await navigator.clipboard.writeText(lines.join('\n'));
        this.flashBtn(this.copyCsvBtn, 'Copied!', 'Copy CSV');
      } catch {
        this.flashBtn(this.copyCsvBtn, 'Copy failed', 'Copy CSV', 1200);
      }
    });
  }
  
  // 버튼에 임시 텍스트를 표시하는 유틸리티 함수
  flashBtn(btn, temp, orig, ms=900){
    const old = btn.textContent; btn.textContent = temp;
    setTimeout(()=> btn.textContent = orig ?? old, ms);
  }

  // 값에 따라 'warn', 'crit' 등급을 반환하는 함수
  classify(key, rawVal){
    const v = Number(rawVal);
    if (!isFinite(v)) return null;
    const rule = this.rules[key];
    return typeof rule === 'function' ? rule(v) : null;
  }

  // 최초 1회, 모든 데이터 키에 대한 테이블 행(DOM)을 생성하는 함수
  initTable(data) {
    const allKeys = Object.keys(data).sort((a,b) => a.localeCompare(b));
    const fragment = document.createDocumentFragment();

    for (const key of allKeys) {
      const tr = document.createElement('tr');
      tr.dataset.key = key;

      const nameTd = document.createElement('td');
      const valueTd = document.createElement('td');
      valueTd.className = 'value';

      const hideBtn = document.createElement('button');
      hideBtn.className = 'hide-btn';
      hideBtn.dataset.action = 'hide';
      hideBtn.dataset.key = key;
      hideBtn.title = '숨기기';
      hideBtn.textContent = '−';

      const unhideBtn = document.createElement('button');
      unhideBtn.className = 'unhide-btn';
      unhideBtn.dataset.action = 'unhide';
      unhideBtn.dataset.key = key;
      unhideBtn.title = '보이기';
      unhideBtn.textContent = '+';
      
      const nameSpan = document.createElement('span');
      nameSpan.textContent = key;
      
      nameTd.append(hideBtn, unhideBtn, nameSpan);
      tr.append(nameTd, valueTd);
      fragment.appendChild(tr);

      // 생성된 DOM 요소들의 참조를 Map에 저장하여 재사용
      this.rows.set(key, { tr, valueTd, hideBtn, unhideBtn, lastVal: undefined });
    }
    this.body.appendChild(fragment);
    this.isInitialized = true;
    this.resortRows(); // 초기 정렬 적용
    this.applyVisibility(); // 초기 숨김 상태 적용
  }
  
  // '중요 키 우선' 토글에 따라 행의 순서를 재정렬하는 함수
  resortRows() {
    const sortedKeys = [...this.rows.keys()];

    if (this.togglePin.checked) {
      const idx = k => { const i = this.importantOrder.indexOf(k); return i === -1 ? 999 : i; };
      sortedKeys.sort((a, b) => idx(a) - idx(b) || a.localeCompare(b));
    } else {
      sortedKeys.sort((a, b) => a.localeCompare(b));
    }

    // 정렬된 순서대로 DOM 요소를 tbody에 다시 추가하여 순서 변경
    sortedKeys.forEach(key => {
      this.body.appendChild(this.rows.get(key).tr);
    });
  }

  // '숨김 키 보기' 토글이나 사용자 설정에 따라 행을 보이거나 숨기는 함수
  applyVisibility() {
    const showHidden = this.toggleHidden.checked;
    for (const [key, { tr, hideBtn, unhideBtn }] of this.rows.entries()) {
      const isBaseHidden = this.baseHidden.includes(key);
      const isUserHidden = this.userHidden.has(key);
      const isHidden = isBaseHidden || isUserHidden;
      
      tr.hidden = isHidden && !showHidden; // `hidden` 속성으로 제어
      hideBtn.style.display = isHidden ? 'none' : 'inline-flex';
      unhideBtn.style.display = isHidden ? 'inline-flex' : 'none';
    }
    this.applyFilter(); // 가시성 변경 후 필터 다시 적용
  }

  // 입력된 텍스트로 테이블을 필터링하는 함수
  applyFilter() {
    const q = this.filterInput.value.trim().toLowerCase();
    this.body.querySelectorAll('tr').forEach(tr => {
      if (tr.hidden && !this.toggleHidden.checked) return; // 이미 숨겨진 행은 무시
      const k = tr.dataset.key.toLowerCase();
      const d = this.rows.get(tr.dataset.key)?.lastVal?.toString().toLowerCase() || '';
      tr.style.display = (k.includes(q) || d.includes(q)) ? '' : 'none';
    });
  }

  // 데이터 업데이트 시 호출되는 메인 함수 (성능 개선의 핵심)
  update(data) {
    if (!data || this.toggleFreeze.checked) return;
    this.lastSnapshot = data;

    if (!this.isInitialized) {
      this.initTable(data);
    }

    // 모든 데이터 키에 대해 반복
    for (const key in data) {
      if (!this.rows.has(key)) continue; // 테이블에 없는 키는 무시

      const { tr, valueTd, lastVal } = this.rows.get(key);
      const raw = data[key];
      const isNum = typeof raw === 'number';
      const display = isNum && !Number.isInteger(raw) ? Number(raw.toFixed(3)) : raw;

      // 값이 실제로 변경되었을 때만 DOM 업데이트 수행
      if (display !== lastVal) {
        valueTd.textContent = display; // 값 텍스트만 변경
        
        const sev = this.classify(key, raw);
        tr.className = sev || ''; // 상태 클래스 변경

        // 값 변경 시 시각적 효과(pulse) 적용
        valueTd.classList.remove('pulse');
        void valueTd.offsetWidth; // 브라우저 리플로우 강제
        valueTd.classList.add('pulse');
        valueTd.title = `prev: ${lastVal}`; // 이전 값을 툴팁으로 표시
        
        this.rows.get(key).lastVal = display; // 마지막 값 업데이트
      }
    }
  }
}
