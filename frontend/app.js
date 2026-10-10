'use strict';
const state = {query:'',category:'all',cost:'all',serviceTag:null,selectedCenterId:null,inquiryOpen:false};
let centers = [], map = null, tiles = null, boundsKey = null, dataLoaded = false;
const markers = new Map();
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const costText = center => ({free:'Free',paid:'Paid',unknown:'Not confirmed'}[center.costStatus]);
const symbol = center => center.category === 'health' ? '✚' : '▤';
const sourceLabel = center => center.isDemo ? 'Demo data' : 'Official source';
function mapStatus(message, retry = true) {
  $('map-status').hidden = !message;
  $('map-status-text').textContent = message;
  $('retry-map').hidden = !retry;
}
function initializeMap() {
  if (!window.L) {
    mapStatus('Map library unavailable. Hospital and learning center information is still available in the list.', false);
    return;
  }
  const reducedMotion = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  try {
    map = L.map('map', {scrollWheelZoom:false, zoomAnimation:!reducedMotion, fadeAnimation:!reducedMotion, markerZoomAnimation:!reducedMotion}).setView([28.455,77.045],12);
    tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom:19, attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
    });
    let failures = 0, pendingTimer;
    tiles.on('loading', () => {
      failures = 0;
      clearTimeout(pendingTimer);
      pendingTimer = setTimeout(() => mapStatus('Map tiles are taking longer to load. You can continue using the provider list.'), 12000);
    });
    tiles.on('tileerror', () => {
      failures++;
      mapStatus('Some map tiles could not load. Check your connection or retry; the provider list and details still work.');
    });
    tiles.on('load', () => {
      clearTimeout(pendingTimer);
      if (!failures) mapStatus('');
    });
    tiles.addTo(map);
    $('retry-map').addEventListener('click', () => {
      mapStatus('Retrying map tiles…');
      tiles.redraw();
    });
    new ResizeObserver(() => map.invalidateSize({pan:false})).observe($('map'));
  } catch {
    mapStatus('Map could not initialize. Continue with the hospital and learning center list.', false);
  }
}
function matches(center) {
  const text = [center.name,center.providerType,center.address,center.locality,...center.services].join(' ').toLowerCase();
  return text.includes(state.query.toLowerCase().trim()) && (state.category === 'all' || center.category === state.category) && (state.cost === 'all' || center.costStatus === state.cost) && (!state.serviceTag || center.serviceTags.includes(state.serviceTag));
}
function update(changes) {if (!dataLoaded) return;Object.assign(state,changes);state.inquiryOpen = false;render();}
function reset() {update({query:'',category:'all',cost:'all',serviceTag:null});}
function selectCenter(id, source) {
  state.selectedCenterId = id;state.inquiryOpen = false;render();
  const marker = markers.get(id);
  if (marker && map) map.panTo(marker.getLatLng(), {animate:false});
  if (source === 'pin' && window.matchMedia('(max-width:760px)').matches) $('details').scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'nearest'});
  $('close-details')?.focus({preventScroll:true});
}
function renderMap(filtered) {
  if (!map) return;
  const ids = new Set(filtered.map(center => center.id));
  for (const [id, marker] of markers) {
    if (!ids.has(id)) {map.removeLayer(marker);markers.delete(id);}
  }
  for (const center of filtered) {
    let marker = markers.get(center.id);
    if (!marker) {
      marker = L.marker([center.latitude,center.longitude], {
        icon:L.divIcon({className:`provider-pin ${center.category}${center.isDemo?' demo':''}`,html:`<span aria-hidden="true">${symbol(center)}</span>`,iconSize:[34,34],iconAnchor:[17,17]}),
        title:`${center.name} — ${center.isDemo?'fictional demo location':'approximate area location'}`,alt:`View ${center.name}`,keyboard:true
      }).addTo(map);
      marker.on('click', () => selectCenter(center.id,'pin'));
      marker.getElement().addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();event.stopPropagation();selectCenter(center.id,'pin');
        }
      });
      markers.set(center.id,marker);
    }
    const element = marker.getElement();
    element.dataset.pin = center.id;
    element.setAttribute('aria-label',`View ${center.name} — ${center.isDemo?'demo':'approximate location'}`);
    element.setAttribute('aria-pressed',String(center.id === state.selectedCenterId));
    marker.setZIndexOffset(center.id === state.selectedCenterId ? 1000 : 0);
  }
  const key = filtered.map(center => center.id).join('|');
  if (key !== boundsKey) {
    boundsKey = key;
    if (filtered.length) map.fitBounds(filtered.map(center => [center.latitude,center.longitude]), {padding:[32,32],maxZoom:14,animate:false});
  }
}
function render() {
  const filtered = centers.filter(matches);
  if (!filtered.some(center => center.id === state.selectedCenterId)) state.selectedCenterId = null;
  $('search').value = state.query;$('cost').value = state.cost;
  document.querySelectorAll('[data-category]').forEach(button => button.setAttribute('aria-pressed',String(button.dataset.category === state.category)));
  $('tag').hidden = !state.serviceTag;
  $('count').innerHTML = `<strong>${filtered.length} ${filtered.length === 1 ? 'center' : 'centers'}</strong> to explore${state.category !== 'all' ? ` · ${state.category === 'health' ? 'Hospitals & health' : 'Learning'}` : ' in Gurgaon'}`;
  $('results').innerHTML = filtered.length ? filtered.map(center => `<button class="center-card" data-center="${escapeHTML(center.id)}" aria-pressed="${center.id === state.selectedCenterId}"><span class="center-icon ${center.category}-icon" aria-hidden="true">${symbol(center)}</span><span class="center-body"><span class="center-top"><span class="category-label ${center.category}-label">${escapeHTML(center.providerType)}</span><span class="demo-label">${sourceLabel(center)}</span></span><strong class="center-name">${escapeHTML(center.name)}</strong><span class="center-locality">${escapeHTML(center.locality)} · Gurgaon</span><span class="services-line">${escapeHTML(center.services.join(' · '))}</span><span class="center-bottom"><span class="cost-badge ${center.costStatus}">${costText(center)}</span>${center.serviceTags.includes('vaccination') ? '<span class="service-badge">Vaccination services</span>' : ''}</span></span><span class="card-arrow" aria-hidden="true">↗</span></button>`).join('') : '<div class="empty-results"><h3>No centers match just yet</h3><p>Try another locality, service, or cost filter.</p><button class="text-button" id="empty-reset">Clear filters and start again ↺</button></div>';
  renderMap(filtered);
  renderDetails();
}
function renderDetails() {
  const center = centers.find(item => item.id === state.selectedCenterId);
  if (!center) {$('details').innerHTML = '<div class="detail-empty"><span aria-hidden="true">⌖</span><h3>A little closer to the right support</h3><p>Select a center from the list or map to explore its services and prepare an inquiry.</p></div>';return;}
  const fact = (label,value,wide=false) => `<div${wide?' class="wide"':''}><dt>${label}</dt><dd>${escapeHTML(value || 'Not confirmed')}</dd></div>`;
  const linkFact = (label,url) => {
    if (!url || !/^https:\/\//i.test(url)) return fact(label,null);
    return `<div class="wide"><dt>${label}</dt><dd><a href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(url)}</a></dd></div>`;
  };
  const message = state.serviceTag === 'vaccination' ? 'Hello, I found your center on Care & Learn. Could you confirm childhood vaccination services, current availability, fees, and how to arrange a visit?' : 'Hello, I found your center on Care & Learn. Could you confirm your services, fees, opening hours, and how to arrange a visit?';
  $('details').innerHTML = `<div class="detail-content"><div class="detail-top"><div><span class="category-label ${center.category}-label">${escapeHTML(center.providerType)} · ${sourceLabel(center)}</span><h3>${escapeHTML(center.name)}</h3><span class="cost-badge ${center.costStatus}">${costText(center)}</span></div><button id="close-details" class="close-button" aria-label="Close center details">×</button></div><p class="detail-address">${escapeHTML(center.address)}</p><div class="detail-services">${center.services.map(service=>`<span>${escapeHTML(service)}</span>`).join('')}</div><dl class="detail-facts">${fact('Fees',center.feeNotes,true)}${fact('Hours',center.hours)}${fact('Age range',center.ageRange)}${fact('Languages',center.languages?.join(', '))}${fact('Contact',center.phone || 'Contact not provided')}${linkFact('Website',center.website)}${fact('Source status',center.sourceStatus)}${center.isDemo?'':linkFact('Official source',center.sourceUrl)+fact('Source checked',center.checkedAt)+fact('Map precision',center.coordinateStatus,true)}</dl><p class="contact-note">${center.isDemo?'Fictional center with no live contact. Review a sample inquiry below.':'Published information checked on '+escapeHTML(center.checkedAt)+'. Confirm services, fees, age eligibility, and the exact location with the provider. WhatsApp availability is not confirmed.'}</p><button id="inquiry" class="inquiry-button" aria-expanded="${state.inquiryOpen}" aria-controls="inquiry-preview">${state.inquiryOpen?'Hide inquiry preview':'Preview WhatsApp inquiry'} <span aria-hidden="true">↗</span></button><div id="inquiry-preview" class="inquiry-box" ${state.inquiryOpen?'':'hidden'}><h4>Your inquiry preview</h4><p class="recipient">For ${escapeHTML(center.name)} · ${center.isDemo?'Fixture contact':'WhatsApp contact not confirmed'}</p><p class="inquiry-message">${escapeHTML(message)}</p><p class="fine-print">Preview only. No message is sent and no WhatsApp link opens.</p></div></div>`;
}
$('search').addEventListener('input',event=>update({query:event.target.value}));
$('cost').addEventListener('change',event=>update({cost:event.target.value}));
document.querySelectorAll('[data-category]').forEach(button=>button.addEventListener('click',()=>update({category:button.dataset.category})));
$('reset').addEventListener('click',reset);
$('tag').addEventListener('click',()=>{update({serviceTag:null});$('reset').focus();});
$('vaccination').addEventListener('click',()=>{update({query:'',category:'health',cost:'all',serviceTag:'vaccination'});$('discovery-title').scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'start'});});
$('results').addEventListener('click',event=>{const button=event.target.closest('[data-center]');if(button) selectCenter(button.dataset.center,'list');if(event.target.closest('#empty-reset')){reset();$('reset').focus();}});
$('details').addEventListener('click',event=>{
  if(event.target.closest('#close-details')){const selected=state.selectedCenterId;update({selectedCenterId:null});document.querySelector(`[data-center="${selected}"]`)?.focus({preventScroll:true});}
  if(event.target.closest('#inquiry')){state.inquiryOpen=!state.inquiryOpen;renderDetails();$('inquiry').focus({preventScroll:true});}
});
initializeMap();
fetch('centers.json').then(response=>{if(!response.ok) throw new Error('Center data load failed');return response.json();}).then(data=>{
  if (!Array.isArray(data) || new Set(data.map(c=>c.id)).size !== data.length || !data.every(c => typeof c.id==='string' && /^[a-z0-9-]+$/.test(c.id) && typeof c.name==='string' && typeof c.address==='string' && typeof c.locality==='string' && ['health','learning'].includes(c.category) && ['free','paid','unknown'].includes(c.costStatus) && Array.isArray(c.services) && Array.isArray(c.serviceTags) && typeof c.isDemo==='boolean' && Number.isFinite(c.latitude) && Math.abs(c.latitude)<=90 && Number.isFinite(c.longitude) && Math.abs(c.longitude)<=180)) throw new Error('Invalid center data');
  centers=data;dataLoaded=true;
  $('hospital-total').textContent=centers.filter(c=>!c.isDemo && c.providerType==='Hospital').length;
  $('learning-total').textContent=centers.filter(c=>!c.isDemo && c.category==='learning').length;
  $('demo-total').textContent=centers.filter(c=>c.isDemo).length;
  render();
}).catch(()=>{
  dataLoaded=false;centers=[];
  $('count').textContent='Center information could not load.';
  $('results').innerHTML='<div class="empty-results"><h3>Unable to load center information</h3><p>Check your connection and serve this folder using the README command, then reload.</p></div>';
  document.querySelectorAll('#search,#cost,[data-category],#reset,#vaccination').forEach(control=>control.disabled=true);
});
