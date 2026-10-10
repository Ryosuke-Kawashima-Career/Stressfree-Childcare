'use strict';
// One filter predicate drives the public provider list and geographic markers.
// Fictional scenarios live in tests/fixtures and enter only through test routing.
const state = {query:'',category:'all',cost:'all',serviceTag:null,selectedCenterId:null,inquiryOpen:false};
let centers = [], map = null, tiles = null, boundsKey = null, dataLoaded = false;
const markers = new Map();
let scopeId = null, submittedQuery = '', retrievalInfo = '', requestGeneration = 0, controller = null, discovering = false;
let retryAction = () => loadSearch();

const $ = id => document.getElementById(id);
const escapeHTML = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const costText = center => ({free:'Free',paid:'Paid',unknown:'Not confirmed'}[center.costStatus]);
const symbol = center => center.category === 'health' ? '✚' : '▤';
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
// Filter responses supply one shared result set for cards and map markers.
function syncControls() {
  $('search').value = state.query; $('cost').value = state.cost;
  document.querySelectorAll('[data-category]').forEach(button => button.setAttribute('aria-pressed',String(button.dataset.category === state.category)));
  $('tag').hidden = !state.serviceTag;
}
function update(changes) {
  Object.assign(state, changes); state.inquiryOpen = false;
  syncControls();
  if ('selectedCenterId' in changes) {render(); return;}
  if (!discovering) loadSearch();
}
function reset() {
  cancelRequest(); scopeId = null; submittedQuery = ''; retrievalInfo = '';
  Object.assign(state,{query:'',category:'all',cost:'all',serviceTag:null});
  syncControls(); loadSearch();
}
function cancelRequest() {
  requestGeneration++; controller?.abort(); discovering = false;
  $('submit-search').disabled = false; $('refresh-search').disabled = false;
}
function searchStatus(message, retry = false) {
  $('search-status').textContent = message; $('retry-search').hidden = !retry;
}
function validateResults(data) {
  if (!Array.isArray(data.items) || new Set(data.items.map(c=>c.id)).size !== data.items.length ||
      !data.items.every(c=>typeof c.id === 'string' && /^[a-z0-9-]+$/.test(c.id) && typeof c.name === 'string' &&
      ['health','learning'].includes(c.category) && ['free','paid','unknown'].includes(c.costStatus) &&
      Array.isArray(c.services) && c.services.every(v=>typeof v==='string') && Array.isArray(c.serviceTags) &&
      Number.isFinite(c.latitude) && Math.abs(c.latitude)<=90 && Number.isFinite(c.longitude) && Math.abs(c.longitude)<=180)) {
    throw new Error('Search returned invalid provider information. Please retry.');
  }
  return data;
}
async function api(path, body, signal) {
  const response = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
  const contentType = response.headers.get('content-type') || '';
  if (!/^application\/(?:[a-z0-9.-]+\+)?json(?:;|$)/i.test(contentType)) {
    throw new Error('The server returned a page instead of API data. Start the FastAPI backend and open the frontend on the same port.');
  }
  let data;
  try {data = await response.json();}
  catch {throw new Error('The backend returned invalid JSON. Please retry or restart the backend.');}

  if (!response.ok) throw new Error(data.error?.message || 'Search request could not be processed. Please retry.');
  return validateResults(data);
}
function applyResults(data) {
  centers = data.items; dataLoaded = true;
  $('hospital-total').textContent = data.directoryCounts.health;
  $('learning-total').textContent = data.directoryCounts.learning;
  render();
}
function showFailure(error) {
  searchStatus(`${error.message || 'Search could not connect. Please retry.'}${dataLoaded ? ' Previous results are still shown.' : ''}`,true);
  if (!dataLoaded) {
    $('count').textContent = 'Center information could not load.';
    $('results').innerHTML = '<div class="empty-results"><h3>Unable to load center information</h3><p>Start the backend, initialize its directory, and retry search.</p></div>';
  }
}
async function loadSearch() {
  cancelRequest();
  const generation = requestGeneration, active = controller = new AbortController();
  retryAction = () => loadSearch();
  searchStatus(dataLoaded ? 'Updating filters… Previous results are still shown.' : 'Loading provider directory…');
  const timer = setTimeout(()=>active.abort(),10000);
  try {
    const data = await api('/api/search',{query:submittedQuery,scopeId,category:state.category,cost:state.cost,serviceTag:state.serviceTag},active.signal);
    if (generation !== requestGeneration) return;
    applyResults(data); searchStatus(retrievalInfo);
    $('refresh-search').hidden = !scopeId;
  } catch(error) {
    if (generation === requestGeneration) showFailure(active.signal.aborted ? new Error('Search timed out. Please retry.') : error);
  } finally {clearTimeout(timer);}
}
async function discover(refresh = false) {
  if (discovering) return;
  const query = state.query.trim(), category = state.category, area = $('area').value;
  cancelRequest(); discovering = true;
  const generation = requestGeneration, active = controller = new AbortController();
  retryAction = () => discover(refresh);
  $('submit-search').disabled = true; $('refresh-search').disabled = true;
  searchStatus('Finding matching stored providers…');
  const timer = setTimeout(()=>active.abort(),35000);
  async function commit(data) {
    if (!/^[a-f0-9]{64}$/.test(data.scopeId)) throw new Error('Search returned an invalid result scope. Please retry.');
    let filtered, filterKey;
    do {
      filterKey = JSON.stringify([state.category,state.cost,state.serviceTag]);
      filtered = await api('/api/search',{query,scopeId:data.scopeId,category:state.category,cost:state.cost,serviceTag:state.serviceTag},active.signal);
      if (generation !== requestGeneration) return false;
    } while (filterKey !== JSON.stringify([state.category,state.cost,state.serviceTag]));
    scopeId = data.scopeId; submittedQuery = query;
    const label = {stored:'Stored results',cached:'Cached results',fresh:'Retrieved results'}[data.retrievalStatus];
    retrievalInfo = `${query ? `Results for “${query}” · ` : ''}${label}${data.retrievalStatus === 'stored' ? '' : ' · '+new Date(data.retrievedAt).toLocaleString()}.${data.warnings?.length ? ' '+data.warnings.join(' ') : ''}`;
    applyResults(filtered); searchStatus(retrievalInfo); $('refresh-search').hidden = !query;
    return true;
  }
  try {
    const saved = await api('/api/reveal',{query,category,area},active.signal);
    if (generation !== requestGeneration) return;
    if (saved.items.length || !query) {
      if (!await commit(saved)) return;
      if (!refresh || !query) return;
    }
    retryAction = () => discover(true);
    searchStatus(`Finding source-backed providers…${saved.items.length ? ' Stored results are shown.' : dataLoaded ? ' Previous results are still shown.' : ''}`);
    const data = await api('/api/discover',{query,category,area,refresh,...(saved.items.length ? {savedScopeId:saved.scopeId} : {})},active.signal);
    if (generation !== requestGeneration) return;
    await commit(data);
  } catch(error) {
    if (generation === requestGeneration) showFailure(active.signal.aborted ? new Error('AI search timed out. Please retry.') : error);
  } finally {
    clearTimeout(timer);
    if (generation === requestGeneration) {discovering = false; $('submit-search').disabled = false; $('refresh-search').disabled = false;}
  }
}
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
        icon:L.divIcon({className:`provider-pin ${center.category}`,html:`<span aria-hidden="true">${symbol(center)}</span>`,iconSize:[34,34],iconAnchor:[17,17]}),
        title:`${center.name} — approximate area location`,alt:`View ${center.name}`,keyboard:true
      }).addTo(map);
      marker.on('click', () => selectCenter(center.id,'pin'));
      marker.getElement().addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();event.stopPropagation();selectCenter(center.id,'pin');
        }
      });
      markers.set(center.id,marker);
    }
    marker.setLatLng([center.latitude,center.longitude]);
    const element = marker.getElement();
    element.dataset.pin = center.id;
    element.setAttribute('aria-label',`View ${center.name} — approximate location`);
    element.setAttribute('aria-pressed',String(center.id === state.selectedCenterId));
    marker.setZIndexOffset(center.id === state.selectedCenterId ? 1000 : 0);
  }
  const key = filtered.map(center => `${center.id}:${center.latitude}:${center.longitude}`).join('|');
  if (key !== boundsKey) {
    boundsKey = key;
    if (filtered.length) map.fitBounds(filtered.map(center => [center.latitude,center.longitude]), {padding:[32,32],maxZoom:14,animate:false});
  }
}
function render() {
  const filtered = centers;
  if (!filtered.some(center => center.id === state.selectedCenterId)) state.selectedCenterId = null;
  $('search').value = state.query;$('cost').value = state.cost;
  document.querySelectorAll('[data-category]').forEach(button => button.setAttribute('aria-pressed',String(button.dataset.category === state.category)));
  $('tag').hidden = !state.serviceTag;
  $('count').innerHTML = `<strong>${filtered.length} ${filtered.length === 1 ? 'center' : 'centers'}</strong> to explore${state.category !== 'all' ? ` · ${state.category === 'health' ? 'Hospitals & health' : 'Learning'}` : ' in Gurgaon'}`;
  $('results').innerHTML = filtered.length ? filtered.map(center => `<button class="center-card" data-center="${escapeHTML(center.id)}" aria-pressed="${center.id === state.selectedCenterId}"><span class="center-icon ${center.category}-icon" aria-hidden="true">${symbol(center)}</span><span class="center-body"><span class="center-top"><span class="category-label ${center.category}-label">${escapeHTML(center.providerType)}</span></span><strong class="center-name">${escapeHTML(center.name)}</strong><span class="center-locality">${escapeHTML(center.locality)}</span><span class="services-line">${escapeHTML(center.services.join(' · '))}</span>${center.relevanceReason ? `<span class="services-line">${escapeHTML(center.relevanceReason)}</span>` : ''}<span class="center-bottom"><span class="cost-badge ${center.costStatus}">${costText(center)}</span>${center.serviceTags.includes('vaccination') ? '<span class="service-badge">Vaccination services</span>' : ''}</span></span><span class="card-arrow" aria-hidden="true">↗</span></button>`).join('') : '<div class="empty-results"><h3>No centers match just yet</h3><p>Try another locality, service, or cost filter.</p><button class="text-button" id="empty-reset">Clear filters and start again ↺</button></div>';
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
  $('details').innerHTML = `<div class="detail-content"><div class="detail-top"><div><span class="category-label ${center.category}-label">${escapeHTML(center.providerType)}</span><h3>${escapeHTML(center.name)}</h3><span class="cost-badge ${center.costStatus}">${costText(center)}</span></div><button id="close-details" class="close-button" aria-label="Close center details">×</button></div><p class="detail-address">${escapeHTML(center.address)}</p><div class="detail-services">${center.services.map(service=>`<span>${escapeHTML(service)}</span>`).join('')}</div>${center.relevanceReason ? `<p>${escapeHTML(center.relevanceReason)}</p>` : ''}<dl class="detail-facts">${fact('Fees',center.feeNotes,true)}${fact('Hours',center.hours)}${fact('Age range',center.ageRange)}${fact('Languages',center.languages?.join(', '))}${fact('Contact',center.phone || 'Contact not provided')}${linkFact('Website',center.website)}${linkFact('Source',center.sourceUrl)}${fact('Information checked',center.checkedAt)}${fact('Map precision',center.coordinateStatus,true)}${fact('Latitude',center.latitude.toFixed(6))}${fact('Longitude',center.longitude.toFixed(6))}${linkFact('Location source',center.coordinateSourceUrl)}${[...new Map((center.citations || []).map(c=>[c.url,c])).values()].map(c=>linkFact(escapeHTML(c.title),c.url)).join('')}</dl><p class="contact-note">Confirm services, fees, age eligibility, and the exact location with the provider. WhatsApp availability is not confirmed.</p><button id="inquiry" class="inquiry-button" aria-expanded="${state.inquiryOpen}" aria-controls="inquiry-preview">${state.inquiryOpen?'Hide inquiry preview':'Preview WhatsApp inquiry'} <span aria-hidden="true">↗</span></button><div id="inquiry-preview" class="inquiry-box" ${state.inquiryOpen?'':'hidden'}><h4>Your inquiry preview</h4><p class="recipient">For ${escapeHTML(center.name)} · WhatsApp contact not confirmed</p><p class="inquiry-message">${escapeHTML(message)}</p><p class="fine-print">Preview only. No message is sent and no WhatsApp link opens.</p></div></div>`;
}
$('search').addEventListener('input',event=>{state.query=event.target.value;});
$('search-form').addEventListener('submit',event=>{event.preventDefault(); discover();});
$('refresh-search').addEventListener('click',()=>discover(true));
$('retry-search').addEventListener('click',()=>retryAction());
$('area').addEventListener('change',()=>{cancelRequest(); scopeId=null; submittedQuery=''; retrievalInfo='Area changed. Submit your phrase to discover providers in this area.'; loadSearch();});
$('cost').addEventListener('change',event=>update({cost:event.target.value}));
document.querySelectorAll('[data-category]').forEach(button=>button.addEventListener('click',()=>update({category:button.dataset.category})));
$('reset').addEventListener('click',reset);
$('tag').addEventListener('click',()=>{update({serviceTag:null});$('reset').focus();});
$('vaccination').addEventListener('click',()=>{cancelRequest();scopeId=null;submittedQuery='';retrievalInfo='';update({query:'',category:'health',cost:'all',serviceTag:'vaccination'});$('discovery-title').scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'start'});});
$('results').addEventListener('click',event=>{const button=event.target.closest('[data-center]');if(button) selectCenter(button.dataset.center,'list');if(event.target.closest('#empty-reset')){reset();$('reset').focus();}});
$('details').addEventListener('click',event=>{
  if(event.target.closest('#close-details')){const selected=state.selectedCenterId;update({selectedCenterId:null});document.querySelector(`[data-center="${selected}"]`)?.focus({preventScroll:true});}
  if(event.target.closest('#inquiry')){state.inquiryOpen=!state.inquiryOpen;renderDetails();$('inquiry').focus({preventScroll:true});}
});
initializeMap();
loadSearch();
