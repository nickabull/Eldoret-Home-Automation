(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const open = $('open-above'), close = $('close-below');
  const format = n => Number(n).toFixed(1).replace(/\.0$/, '') + '°C';
  const finite = n => typeof n === 'number' && Number.isFinite(n);
  function rule() {
    let hot = Number(open.value), cool = Number(close.value);
    if (cool >= hot) {
      if (document.activeElement === close) hot = Math.min(26, cool + 0.5);
      else cool = Math.max(18, hot - 0.5);
      if (cool >= hot) { hot = 26; cool = 25.5; }
      open.value = String(hot); close.value = String(cool);
    }
    $('open-above-value').textContent = format(hot);
    $('close-below-value').textContent = format(cool);
    $('velux-rule').innerHTML = '<strong>Proposed rule — NOT ACTIVE</strong><div>Above ' + format(hot) + ': ask the windows to open for cooling. Below ' + format(cool) + ': close them. Between these values: keep their previous state.</div><div>Rain, stale sensor values or a manual override must prevent automatic opening.</div>';
    $('velux-save-state').textContent = 'Unsaved draft · no commands sent';
  }
  for (const slider of [open, close]) slider.addEventListener('input', rule);
  try {
    const saved = JSON.parse(localStorage.getItem('eldoret-velux-comfort-draft') || 'null');
    if (saved && Number.isFinite(saved.open) && Number.isFinite(saved.close) &&
        saved.close >= 18 && saved.open <= 26 && saved.open > saved.close) {
      open.value = String(saved.open); close.value = String(saved.close);
    }
  } catch (_) {}
  rule();
  $('velux-save').addEventListener('click', () => {
    try {
      localStorage.setItem('eldoret-velux-comfort-draft',
        JSON.stringify({open: Number(open.value), close: Number(close.value)}));
      $('velux-save-state').textContent = 'Draft saved in this browser · automation OFF';
    } catch (_) {
      $('velux-save-state').textContent = 'Browser could not save draft · automation OFF';
    }
  });
  let busy = false;
  async function refresh() {
    if (busy || document.hidden) return;
    busy = true;
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 24000);
    try {
      const response = await fetch('/api/velux/homekit', {cache:'no-store', signal: abort.signal});
      if (!response.ok) throw new Error('Local API did not respond');
      const data = await response.json();
      const fresh = data.checked_at && Date.now() - Date.parse(data.checked_at) < 90000 && Date.now() - Date.parse(data.checked_at) > -10000;
      if (!data.connected || !fresh) throw new Error(data.error || 'No fresh sensor reading');
      $('velux-link').textContent = 'LOCAL · CONNECTED';
      $('velux-checked').textContent = 'Updated ' + new Date(data.checked_at).toLocaleTimeString('en-GB') + ' · sensor readings';
      const c = data.climate || {};
      $('velux-temp').textContent = finite(c.temperature) ? c.temperature.toFixed(1) : '—';
      $('velux-humidity').textContent = finite(c.humidity) ? c.humidity.toFixed(0) + '%' : '—';
      $('velux-co2').textContent = finite(c.co2_ppm) ? c.co2_ppm.toFixed(0) : '—';
      for (const aid of [3,4]) {
        const w = (data.windows || []).find(w => w.aid === aid);
        $('velux-w' + aid).textContent = w && finite(w.current_position) ? w.current_position + '% open' : '—';
      }
      $('velux-window-state').textContent = 'Both window positions are monitored locally. Movement is disabled in Eldoret pending supervised safety checks.';
    } catch (e) {
      $('velux-link').textContent = 'READING UNAVAILABLE';
      $('velux-checked').textContent = 'No fresh HomeKit reading · ' + String(e.message || 'check Bulldog');
      $('velux-temp').textContent = '—';
      $('velux-humidity').textContent = '—';
      $('velux-co2').textContent = '—';
      $('velux-w3').textContent = '—'; $('velux-w4').textContent = '—';
      $('velux-window-state').textContent = 'Waiting for a live window-position update.';
    } finally { clearTimeout(timeout); busy = false; }
  }
  refresh();
  setInterval(refresh, 30000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
