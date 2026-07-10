// ══════════════════════════════════════════
// 누리보이스 IMS - 메인 JavaScript
// ══════════════════════════════════════════

// ── 현재 날짜/시간 표시 ──
function updateDateTime() {
  const el = document.getElementById('currentDateTime');
  if (!el) return;
  const now = new Date();
  const days = ['일','월','화','수','목','금','토'];
  const y = now.getFullYear();
  const m = String(now.getMonth()+1).padStart(2,'0');
  const d = String(now.getDate()).padStart(2,'0');
  const day = days[now.getDay()];
  const h = String(now.getHours()).padStart(2,'0');
  const min = String(now.getMinutes()).padStart(2,'0');
  el.textContent = `${y}.${m}.${d} (${day}) ${h}:${min}`;
}
updateDateTime();
setInterval(updateDateTime, 30000);

// ── 사이드바 토글 ──
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const main = document.querySelector('.main-wrapper');
  if (sidebar) sidebar.classList.toggle('collapsed');
  if (main) main.classList.toggle('expanded');
}

// ── 사이드바 서브메뉴 그룹 토글 ──
function toggleNavGroup(id) {
  const group = document.getElementById(id);
  if (group) group.classList.toggle('open');
}

// ── 알림 메시지 자동 숨김 ──
document.querySelectorAll('.flash-msg').forEach(msg => {
  setTimeout(() => {
    msg.style.transition = 'opacity 0.5s';
    msg.style.opacity = '0';
    setTimeout(() => msg.remove(), 500);
  }, 5000);
});

// ── 통계 숫자 카운트업 애니메이션 ──
function animateCounter(el, target) {
  let start = 0;
  const duration = 800;
  const step = target / (duration / 16);
  const timer = setInterval(() => {
    start = Math.min(start + step, target);
    el.textContent = Math.floor(start);
    if (start >= target) clearInterval(timer);
  }, 16);
}

document.querySelectorAll('.stat-value, .iso-stat-num').forEach(el => {
  const val = parseInt(el.textContent, 10);
  if (!isNaN(val) && val > 0) {
    el.textContent = '0';
    setTimeout(() => animateCounter(el, val), 200);
  }
});

// ── ISO 프로그레스 바 애니메이션 ──
document.querySelectorAll('.iso-bar-fill').forEach(bar => {
  const width = bar.style.width;
  bar.style.width = '0%';
  setTimeout(() => { bar.style.width = width; }, 300);
});

// ── 툴팁 ──
document.querySelectorAll('[data-tooltip]').forEach(el => {
  el.addEventListener('mouseenter', function() {
    const tip = document.createElement('div');
    tip.className = 'tooltip';
    tip.textContent = this.dataset.tooltip;
    tip.style.cssText = `
      position:fixed;background:#1e293b;color:white;
      padding:6px 10px;border-radius:6px;font-size:0.75rem;
      pointer-events:none;z-index:9999;white-space:nowrap;
    `;
    document.body.appendChild(tip);
    const rect = this.getBoundingClientRect();
    tip.style.top = (rect.top - tip.offsetHeight - 8) + 'px';
    tip.style.left = (rect.left + rect.width/2 - tip.offsetWidth/2) + 'px';
    this._tooltip = tip;
  });
  el.addEventListener('mouseleave', function() {
    if (this._tooltip) { this._tooltip.remove(); this._tooltip = null; }
  });
});

// ── 폼 입력 유효성 표시 ──
document.querySelectorAll('.form-control, .form-input').forEach(input => {
  input.addEventListener('blur', function() {
    if (this.hasAttribute('required') && !this.value.trim()) {
      this.style.borderColor = 'var(--danger)';
    } else {
      this.style.borderColor = '';
    }
  });
  input.addEventListener('input', function() {
    this.style.borderColor = '';
  });
});

// ── 테이블 행 클릭 ──
document.querySelectorAll('tr[data-href]').forEach(row => {
  row.style.cursor = 'pointer';
  row.addEventListener('click', () => { window.location.href = row.dataset.href; });
});

// ── 삭제 확인 ──
document.querySelectorAll('[data-confirm]').forEach(el => {
  el.addEventListener('click', function(e) {
    if (!confirm(this.dataset.confirm || '정말 삭제하시겠습니까?')) {
      e.preventDefault();
    }
  });
});

console.log('✅ 누리보이스 IMS v1.0 초기화 완료');
