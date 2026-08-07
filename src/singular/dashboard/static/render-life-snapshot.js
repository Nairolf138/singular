import {fetchJson} from './api.js';
import {getSelectedLife,SELECTED_LIFE_CHANGED_EVENT} from './state.js';

const escapeHtml=value=>String(value??'Non disponible').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');

const renderSnapshot=payload=>{
  const title=document.getElementById('life-snapshot-title');
  if(title){title.textContent=`Fiche synthétique · ${payload.life}`;}
  for(const node of document.querySelectorAll('[data-snapshot-field]')){
    node.textContent=payload.summary?.[node.dataset.snapshotField]??'Non disponible';
  }
  const evidence=document.getElementById('life-snapshot-evidence-content');
  if(evidence){
    const items=payload.evidence||[];
    evidence.innerHTML=items.length?items.map(item=>`<div class='snapshot-proof'><strong>${escapeHtml(item.kind)}</strong> · ${escapeHtml(item.at)}<br>${escapeHtml(item.description)}</div>`).join(''):'Aucune preuve disponible.';
  }
  const raw=document.getElementById('life-snapshot-raw-content');
  if(raw){raw.textContent=JSON.stringify(payload.technical||{},null,2);}
};

const loadSnapshot=async life=>{
  const panel=document.getElementById('life-snapshot');
  if(!panel){return;}
  if(!life){panel.classList.add('panel-hidden');return;}
  panel.classList.remove('panel-hidden');
  const title=document.getElementById('life-snapshot-title');
  if(title){title.textContent=`Fiche synthétique · ${life} · chargement…`;}
  try{renderSnapshot(await fetchJson(`/api/lives/${encodeURIComponent(life)}/snapshot`));}
  catch(error){if(title){title.textContent=`Fiche synthétique · ${life} · indisponible`;}}
};

export const bindLifeSnapshot=()=>{
  window.addEventListener(SELECTED_LIFE_CHANGED_EVENT,event=>loadSnapshot(event.detail?.name));
  loadSnapshot(getSelectedLife());
};
