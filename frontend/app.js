'use strict';
const state = {query:'',category:'all',cost:'all',serviceTag:null,selectedCenterId:null,inquiryOpen:false};
let centers = [];
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const costText = center => ({free:'Free',paid:'Paid',unknown:'Not confirmed'}[center.costStatus]);
const symbol = center => center.category === 'health' ? '✚' : '▤';
function matches(center) {
  const text = [center.name,center.address,center.locality,...center.services].join(' ').toLowerCase();
  return text.includes(state.query.toLowerCase().trim()) && (state.category === 'all' || center.category === state.category) && (state.cost === 'all' || center.costStatus === state.cost) && (!state.serviceTag || center.serviceTags.includes(state.serviceTag));
}
function update(changes) {Object.assign(state,changes);state.inquiryOpen = false;render();}
function reset() {update({query:'',category:'all',cost:'all',serviceTag:null});}
function selectCenter(id, source) {
  state.selectedCenterId = id;state.inquiryOpen = false;render();
  if (source === 'pin' && window.matchMedia('(max-width:760px)').matches) $('details').scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'nearest'});
  $('close-details')?.focus({preventScroll:true});
}
function render() {
  const filtered = centers.filter(matches);
  if (!filtered.some(center => center.id === state.selectedCenterId)) state.selectedCenterId = null;
  $('search').value = state.query;$('cost').value = state.cost;
  document.querySelectorAll('[data-category]').forEach(button => button.setAttribute('aria-pressed',String(button.dataset.category === state.category)));
  $('tag').hidden = !state.serviceTag;
  $('count').innerHTML = `<strong>${filtered.length} ${filtered.length === 1 ? 'center' : 'centers'}</strong> to explore${state.category !== 'all' ? ` · ${state.category === 'health' ? 'Health' : 'Learning'}` : ' in Gurgaon'}`;
  $('results').innerHTML = filtered.length ? filtered.map(center => `<button class="center-card" data-center="${center.id}" aria-pressed="${center.id === state.selectedCenterId}"><span class="center-icon ${center.category}-icon" aria-hidden="true">${symbol(center)}</span><span class="center-body"><span class="center-top"><span class="category-label ${center.category}-label">${center.category}</span><span class="demo-label">Demo data</span></span><strong class="center-name">${escapeHTML(center.name)}</strong><span class="center-locality">${escapeHTML(center.locality)} · Gurgaon</span><span class="services-line">${escapeHTML(center.services.join(' · '))}</span><span class="center-bottom"><span class="cost-badge ${center.costStatus}">${costText(center)}</span>${center.serviceTags.includes('vaccination') ? '<span class="service-badge">Vaccination services</span>' : ''}</span></span><span class="card-arrow" aria-hidden="true">↗</span></button>`).join('') : '<div class="empty-results"><h3>No centers match just yet</h3><p>Try another locality, service, or cost filter.</p><button class="text-button" id="empty-reset">Clear filters and start again ↺</button></div>';
  $('pins').innerHTML = filtered.map(center => {
    // Derived from fixture coordinates; this is an illustration, not a geographic map.
    const x = 16 + (center.longitude - 77.034) / (77.075 - 77.034) * 70;
    const y = 20 + (28.472 - center.latitude) / (28.472 - 28.439) * 53;
    return `<button class="pin ${center.category}" style="left:${x}%;top:${y}%" data-pin="${center.id}" aria-label="View ${escapeHTML(center.name)}" aria-pressed="${center.id === state.selectedCenterId}" title="${escapeHTML(center.name)}"><span aria-hidden="true">${symbol(center)}</span></button>`;
  }).join('');
  renderDetails();
}
function renderDetails() {
  const center = centers.find(item => item.id === state.selectedCenterId);
  if (!center) {$('details').innerHTML = '<div class="detail-empty"><span aria-hidden="true">⌖</span><h3>A little closer to the right support</h3><p>Select a center from the list or map to explore its services and prepare an inquiry.</p></div>';return;}
  const fact = (label,value,wide=false) => `<div${wide?' class="wide"':''}><dt>${label}</dt><dd>${escapeHTML(value || 'Not confirmed')}</dd></div>`;
  const message = state.serviceTag === 'vaccination' ? 'Hello, I found your center on Care & Learn. Could you confirm childhood vaccination services, current availability, fees, and how to arrange a visit?' : 'Hello, I found your center on Care & Learn. Could you confirm your services, fees, opening hours, and how to arrange a visit?';
  $('details').innerHTML = `<div class="detail-content"><div class="detail-top"><div><span class="category-label ${center.category}-label">${center.category} · Demo data</span><h3>${escapeHTML(center.name)}</h3><span class="cost-badge ${center.costStatus}">${costText(center)}</span></div><button id="close-details" class="close-button" aria-label="Close center details">×</button></div><p class="detail-address">${escapeHTML(center.address)}</p><div class="detail-services">${center.services.map(service=>`<span>${escapeHTML(service)}</span>`).join('')}</div><dl class="detail-facts">${fact('Fees',center.feeNotes,true)}${fact('Hours',center.hours)}${fact('Age range',center.ageRange)}${fact('Languages',center.languages?.join(', '))}${fact('Contact',center.phone || 'Contact not provided')}${fact('Website',center.website)}${fact('Source status',center.sourceStatus)}</dl><p class="contact-note">Fictional center with no live contact. Review a sample inquiry below.</p><button id="inquiry" class="inquiry-button" aria-expanded="${state.inquiryOpen}" aria-controls="inquiry-preview">${state.inquiryOpen?'Hide inquiry preview':'Preview WhatsApp inquiry'} <span aria-hidden="true">↗</span></button><div id="inquiry-preview" class="inquiry-box" ${state.inquiryOpen?'':'hidden'}><h4>Your inquiry preview</h4><p class="recipient">For ${escapeHTML(center.name)} · Fixture contact</p><p class="inquiry-message">${escapeHTML(message)}</p><p class="fine-print">Preview only. No message is sent and no WhatsApp link opens.</p></div></div>`;
}
$('search').addEventListener('input',event=>update({query:event.target.value}));
$('cost').addEventListener('change',event=>update({cost:event.target.value}));
document.querySelectorAll('[data-category]').forEach(button=>button.addEventListener('click',()=>update({category:button.dataset.category})));
$('reset').addEventListener('click',reset);
$('tag').addEventListener('click',()=>{update({serviceTag:null});$('reset').focus();});
$('vaccination').addEventListener('click',()=>{update({query:'',category:'health',cost:'all',serviceTag:'vaccination'});$('discovery-title').scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'start'});});
$('results').addEventListener('click',event=>{const button=event.target.closest('[data-center]');if(button) selectCenter(button.dataset.center,'list');if(event.target.closest('#empty-reset')){reset();$('reset').focus();}});
$('pins').addEventListener('click',event=>{const button=event.target.closest('[data-pin]');if(button) selectCenter(button.dataset.pin,'pin');});
$('details').addEventListener('click',event=>{
  if(event.target.closest('#close-details')){const selected=state.selectedCenterId;update({selectedCenterId:null});document.querySelector(`[data-center="${selected}"]`)?.focus({preventScroll:true});}
  if(event.target.closest('#inquiry')){state.inquiryOpen=!state.inquiryOpen;renderDetails();$('inquiry').focus({preventScroll:true});}
});
fetch('centers.json').then(response=>{if(!response.ok) throw new Error('Fixture load failed');return response.json();}).then(data=>{centers=data;render();}).catch(()=>{$('count').textContent='Demo centers could not load.';$('results').innerHTML='<div class="empty-results"><h3>Unable to load the demo</h3><p>Serve this folder with the local HTTP command in the README, then reload.</p></div>';});
