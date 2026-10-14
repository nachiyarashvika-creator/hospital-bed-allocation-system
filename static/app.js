'use strict';
let state;
let pending = false;
const $ = selector => document.querySelector(selector);
// Escape all text from the database before inserting HTML (including names).
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const displayStatus = value => value === 'ready' ? 'Ready' : value[0].toUpperCase() + value.slice(1);
function notice(message, error = false) { $('#notice').textContent = message; $('#notice').className = error ? 'error' : ''; }
async function api(path, data) {
  const response = await fetch('/api/' + path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed.');
  return result;
}
function formData(form) { const data = Object.fromEntries(new FormData(form)); data.severity = Number(data.severity); return data; }
function patientTable(patients, waiting = false) {
  if (!patients.length) return '<p>No patients here.</p>';
  return '<table><thead><tr><th>Patient</th><th>Condition</th><th>Severity</th><th>Bed / status</th><th>Action</th></tr></thead><tbody>' + patients.map(p => {
    const bed = state.beds.find(b => b.id === p.bed_id);
    return `<tr><td>${esc(p.name)}<br><small>${esc(p.gender)}</small></td><td>${esc(p.condition)}</td><td><span class="badge">${p.severity} / 5</span></td><td>${esc(bed ? bed.label : 'Waiting')} · ${esc(p.status)}</td><td>${p.status === 'reserved' ? `<button data-confirm="${p.id}">Confirm admission</button>` : ''}<button class="secondary" data-discharge="${p.id}">${waiting || p.status === 'reserved' ? 'Cancel' : 'Discharge'}</button></td></tr>`;
  }).join('') + '</tbody></table>';
}
function render() {
  const counts = Object.fromEntries(['ready','occupied','cleaning','reserved'].map(s => [s, state.beds.filter(b => b.status === s).length]));
  $('#stats').innerHTML = Object.entries({...counts,waiting:state.patients.filter(p => p.status === 'waiting').length}).map(([s,n]) => `<div class="stat"><span>${esc(displayStatus(s))}</span><strong>${n}</strong></div>`).join('');
  $('#heatmap').innerHTML = state.wards.map(w => `<div class="ward"><h3>${esc(w.name)} <small>· ${esc(w.gender)}</small></h3><div class="beds">${state.beds.filter(b => b.ward_id === w.id).map(b => `<div class="bed ${b.status}" aria-label="${esc(b.label)} ${b.status}"><strong>${esc(b.label)}</strong><small>${esc(b.kind)}${b.ventilator ? ' · ventilator' : ''}</small><small>${displayStatus(b.status)}</small></div>`).join('')}</div></div>`).join('');
  $('#active-patients').innerHTML = patientTable(state.patients.filter(p => ['admitted','reserved'].includes(p.status)));
  $('#waiting-patients').innerHTML = patientTable(state.patients.filter(p => p.status === 'waiting'), true);
  $('#cleaning-beds').innerHTML = state.beds.filter(b => b.status === 'cleaning').map(b => `<div class="cleaning-card">${esc(b.label)} · ${esc(b.kind)}<strong>${Math.max(0,Math.ceil(b.cleaning_until - state.server_time))} seconds remaining</strong></div>`).join('') || '<p>No beds are currently being cleaned.</p>';
  $('#staff').textContent = 'Demo staff: ' + state.staff.map(p => `${p.name} (${p.role})`).join(' · ');
}
async function refresh() {
  try { state = await api('state'); render(); $('#connection').textContent = '● Live · SQLite connected'; }
  catch (error) { $('#connection').textContent = 'Offline · retrying'; notice(error.message, true); }
}
async function action(work) {
  if (pending) return;
  pending = true;
  document.querySelectorAll('form button').forEach(b => b.disabled = true);
  try { await work(); await refresh(); } catch (error) { notice(error.message, true); }
  finally { pending = false; document.querySelectorAll('form button').forEach(b => b.disabled = false); }
}
document.querySelectorAll('nav button').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.page').forEach(p => p.hidden = p.id !== button.dataset.page);
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('active', b === button));
  $('#page-title').textContent = button.textContent;
}));
$('#suggest').addEventListener('click', () => { const form = $('#admit-form'); if (!form.reportValidity()) return; action(async () => { const result = await api('suggest',formData(form)); notice(result.bed ? `Suggested: ${result.bed.label} in ${result.bed.ward_name}. This is a suggestion; the bed is not reserved.` : 'No suitable ready bed. Admission will add the patient to the waiting list.'); }); });
$('#admit-form').addEventListener('submit', event => { event.preventDefault(); action(async () => { const result = await api('admit',formData(event.target)); notice(result.bed ? `Patient admitted to ${result.bed.label}.` : 'Patient added to the priority waiting list.'); event.target.reset(); }); });
$('#emergency-form').addEventListener('submit', event => { event.preventDefault(); action(async () => {
  const result = await api('emergency',formData(event.target));
  notice(result.bed ? `Emergency bed ${result.bed.label} reserved (${result.bed.distance} m). Confirm admission on the Discharge & reservations page.` : 'No suitable critical-care bed. Patient added to the waiting list.');
  $('#shift-result').innerHTML = result.shift_suggestions.length ? '<h3>Doctor review needed</h3>' + result.shift_suggestions.map(s => `<p>${esc(s.name)}: ${esc(s.from)} → ${esc(s.to)} (stable general-care patient).</p>`).join('') : (result.bed ? '' : '<p>No safe transfer candidate with a ready general bed was found.</p>');
  event.target.reset();
}); });
document.addEventListener('click', event => { const button = event.target.closest('[data-discharge],[data-confirm]'); if (!button) return; action(async () => { const id = button.dataset.confirm || button.dataset.discharge; const operation = button.dataset.confirm ? 'confirm' : 'discharge'; const result = await api(`patients/${id}/${operation}`,{}); notice(result.message); }); });
refresh();
setInterval(() => { if (!pending) refresh(); }, 2000);
