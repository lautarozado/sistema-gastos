/* ================================================
   SISTEMA DE GASTOS — JavaScript Principal
   ================================================ */

// ── Sidebar (mobile) ─────────────────────────────
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('show');
  document.getElementById('sidebarOverlay').classList.toggle('show');
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('show');
  document.getElementById('sidebarOverlay').classList.remove('show');
}

// ── FAB ──────────────────────────────────────────
function toggleFab() {
  const opts = document.getElementById('fabOptions');
  const btn  = document.getElementById('fabMain');
  if (opts && btn) {
    opts.classList.toggle('show');
    btn.classList.toggle('open');
  }
}
document.addEventListener('click', function(e) {
  const fab = document.querySelector('.fab-container');
  if (fab && !fab.contains(e.target)) {
    document.getElementById('fabOptions')?.classList.remove('show');
    document.getElementById('fabMain')?.classList.remove('open');
  }
});

// ── Auto-dismiss alerts (5 s) ────────────────────
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.alert.alert-dismissible').forEach(function(el) {
    setTimeout(function() {
      try { bootstrap.Alert.getOrCreateInstance(el).close(); } catch(e) {}
    }, 5000);
  });
});

// ── Formato moneda ────────────────────────────────
function fmtMoney(v, sym) {
  sym = sym || '$';
  const n = parseFloat(v) || 0;
  return sym + ' ' + n.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── Formateo de inputs de monto (1.000.000,50) ────
function montoToMachine(str) {
  if (!str) return '';
  str = String(str).trim();
  // Argentine display format (comma = decimal): strip thousands dots, swap comma→dot
  if (str.indexOf(',') >= 0) return str.replace(/\./g, '').replace(',', '.');
  return str; // already machine format
}

function montoFormat(val) {
  var s = String(val).trim();
  if (!s) return '';
  // Normalize to machine first
  var normalized = (s.indexOf(',') >= 0)
    ? s.replace(/\./g, '').replace(',', '.')
    : s;
  var parts = normalized.split('.');
  var intPart = (parts[0] || '').replace(/\D/g, '') || '';
  var decPart = parts.length > 1 ? parts[1].replace(/\D/g, '').substring(0, 2) : '';
  if (!intPart) return '';
  intPart = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return decPart ? intPart + ',' + decPart : intPart;
}

function initMontoInput(el) {
  if (typeof el === 'string') el = document.getElementById(el);
  if (!el) return;
  // Format existing value (e.g. when editing)
  if (el.value) el.value = montoFormat(el.value);
  el.addEventListener('input', function() {
    var start = this.selectionStart;
    var oldLen = this.value.length;
    // Allow only digits and one comma (decimal)
    var raw = this.value.replace(/[^\d,]/g, '');
    var ci = raw.indexOf(',');
    if (ci >= 0) raw = raw.substring(0, ci + 1) + raw.substring(ci + 1).replace(/,/g, '');
    var parts = raw.split(',');
    var intPart = (parts[0] || '').replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    var formatted = parts.length > 1 ? intPart + ',' + parts[1].substring(0, 2) : intPart;
    this.value = formatted;
    var newPos = Math.max(0, start + (formatted.length - oldLen));
    try { this.setSelectionRange(newPos, newPos); } catch(e) {}
  });
}

// ── Chart.js defaults ─────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  if (typeof Chart === 'undefined') return;
  Chart.defaults.font.family = '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif';
  Chart.defaults.font.size   = 12;
  Chart.defaults.color       = '#64748b';
  Chart.defaults.plugins.legend.labels.padding       = 18;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.pointStyleWidth = 10;
  Chart.defaults.plugins.tooltip.padding          = 10;
  Chart.defaults.plugins.tooltip.cornerRadius     = 8;
  Chart.defaults.plugins.tooltip.backgroundColor  = '#1e293b';
  Chart.defaults.plugins.tooltip.titleColor       = '#f1f5f9';
  Chart.defaults.plugins.tooltip.bodyColor        = '#cbd5e1';
  Chart.defaults.plugins.tooltip.displayColors    = true;
});

// Paleta de colores para charts
const CHART_PALETTE = [
  '#4361ee','#10b981','#f59e0b','#ef4444','#8b5cf6',
  '#06b6d4','#f97316','#ec4899','#14b8a6','#64748b'
];

// ── Cargar subcategorías dinámicamente ─────────────
function loadSubcategorias(catId, selectEl, currentSubId) {
  selectEl.innerHTML = '<option value="">Sin subcategoría</option>';
  if (!catId) return;
  fetch('/gastos/api/subcategorias/' + catId)
    .then(function(r){ return r.json(); })
    .then(function(data){
      data.forEach(function(s){
        var opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.nombre;
        if (currentSubId && String(s.id) === String(currentSubId)) opt.selected = true;
        selectEl.appendChild(opt);
      });
    })
    .catch(function(){});
}

// ── Validación medios de cobro (ingresos) ──────────
function initPaymentValidation() {
  const totalInput   = document.getElementById('total');
  const medioInputs  = document.querySelectorAll('.medio-monto');
  const summaryEl    = document.getElementById('paymentSummary');
  const submitBtn    = document.getElementById('submitIngreso');

  if (!totalInput || !medioInputs.length) return;

  function recalc() {
    var total = parseFloat(montoToMachine(totalInput.value)) || 0;
    var suma  = 0;
    medioInputs.forEach(function(inp){
      suma += parseFloat(montoToMachine(inp.value)) || 0;
    });
    var diff = total - suma;
    if (summaryEl) {
      if (Math.abs(diff) < 0.01) {
        summaryEl.innerHTML =
          '<i class="bi bi-check-circle-fill text-success me-1"></i>' +
          '<strong class="text-success">Los medios suman el total correctamente.</strong>';
        summaryEl.className = 'mt-2 p-2 rounded';
        summaryEl.style.background = '#ecfdf5';
        if (submitBtn) submitBtn.disabled = false;
      } else {
        var sign = diff > 0 ? '+' : '';
        summaryEl.innerHTML =
          '<i class="bi bi-exclamation-circle-fill text-danger me-1"></i>' +
          'Diferencia: <strong class="text-danger">' + sign + fmtMoney(diff) + '</strong> ' +
          '(suma actual: ' + fmtMoney(suma) + ' / total: ' + fmtMoney(total) + ')';
        summaryEl.className = 'mt-2 p-2 rounded';
        summaryEl.style.background = '#fef2f2';
        if (submitBtn) submitBtn.disabled = (total > 0);
      }
    }
  }

  totalInput.addEventListener('input', recalc);
  medioInputs.forEach(function(inp){ inp.addEventListener('input', recalc); });
  recalc(); // inicial
}

// Distribuir total en efectivo automáticamente
function distribuirEnEfectivo() {
  var total = parseFloat(montoToMachine(document.getElementById('total')?.value || '')) || 0;
  document.querySelectorAll('.medio-monto').forEach(function(inp){ inp.value = ''; });
  var efectivo = document.getElementById('medio_efectivo');
  if (efectivo && total > 0) {
    efectivo.value = montoFormat(total.toFixed(2));
  }
  document.querySelectorAll('.medio-monto').forEach(function(i){ i.dispatchEvent(new Event('input')); });
}

// ── Confirmación de eliminación ───────────────────
function confirmarEliminar(form, nombre) {
  var msg = nombre
    ? '¿Eliminar definitivamente "' + nombre + '"? Esta acción no se puede deshacer.'
    : '¿Eliminar definitivamente? Esta acción no se puede deshacer.';
  if (confirm(msg)) form.submit();
}
function confirmarAnular(form) {
  if (confirm('¿Anular este registro? Quedará marcado como anulado pero no se borrará.')) form.submit();
}

// ── Helpers de modal con datos ────────────────────
function fillModal(modalId, data) {
  var modal = document.getElementById(modalId);
  if (!modal) return;
  Object.keys(data).forEach(function(k){
    var el = modal.querySelector('[name="' + k + '"]');
    if (!el) return;
    if (el.type === 'checkbox') el.checked = !!data[k];
    else el.value = data[k] !== null && data[k] !== undefined ? data[k] : '';
  });
}
