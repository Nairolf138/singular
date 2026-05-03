import {normalizeItem} from './render-quests.js';
import {runAction} from './actions.js';

const conversationState={
  selectedLife:'',
  flow:'indisponible',
  historyByLife:new Map(),
  lastMetaByLife:new Map(),
};

const FLOW_STYLES={
  'en écoute':'summary-ok',
  'en réflexion':'summary-warning',
  'indisponible':'summary-muted',
  'arrêtée':'summary-critical',
};

const bindJsonToggle=(buttonId,rawId)=>{
  const button=document.getElementById(buttonId);
  const raw=document.getElementById(rawId);
  if(!button||!raw||button.dataset.bound==='true'){return;}
  button.dataset.bound='true';
  button.addEventListener('click',()=>{
    const isHidden=raw.classList.contains('panel-hidden');
    raw.classList.toggle('panel-hidden',!isHidden);
    button.textContent=isHidden?'Masquer JSON':'Voir JSON';
    button.setAttribute('aria-expanded',isHidden?'true':'false');
  });
};

const setFlowState=(flow)=>{
  conversationState.flow=flow;
  const el=document.getElementById('conversation-flow-state');
  if(!el){return;}
  el.textContent=`État: ${flow}`;
  el.className=`summary-pill ${FLOW_STYLES[flow]||'summary-muted'}`;
};

const inferFlow=(meta)=>{
  const status=String(meta?.status||'').toLowerCase();
  if(status.includes('stop')||status.includes('dead')||status.includes('archiv')){return 'arrêtée';}
  if(status.includes('busy')||status.includes('thinking')||status.includes('processing')){return 'en réflexion';}
  if(status.includes('available')||status.includes('ready')||status.includes('active')){return 'en écoute';}
  return 'indisponible';
};

const renderHistory=(life)=>{
  const historyEl=document.getElementById('conversation-history');
  if(!historyEl){return;}
  const history=conversationState.historyByLife.get(life)||[];
  if(!history.length){historyEl.textContent='Aucun message.';return;}
  historyEl.innerHTML=history.slice(-8).map(item=>`<div><strong>${item.role}:</strong> ${item.text}</div>`).join('');
};

const renderMeta=(life)=>{
  const meta=conversationState.lastMetaByLife.get(life)||{};
  document.getElementById('conversation-selected-life').textContent=`Vie: ${life||'aucune sélection'}`;
  document.getElementById('conversation-availability').textContent=`Disponibilité: ${meta.status||'inconnue'}`;
  document.getElementById('conversation-last-activity').textContent=`Activité récente: ${meta.last_update||'non disponible'}`;
  const history=conversationState.historyByLife.get(life)||[];
  const lastMsg=history.length?history[history.length-1].text:'aucun';
  document.getElementById('conversation-last-message').textContent=`Dernier message: ${lastMsg}`;
  setFlowState(inferFlow(meta));
  renderHistory(life);
};

const bindSend=(rows)=>{
  const sendBtn=document.getElementById('conversation-send');
  const input=document.getElementById('conversation-input');
  if(!sendBtn||sendBtn.dataset.bound==='true'||!input){return;}
  sendBtn.dataset.bound='true';
  sendBtn.addEventListener('click',async ()=>{
    const life=conversationState.selectedLife;
    const text=input.value.trim();
    if(!life||!text){setFlowState('indisponible');return;}
    setFlowState('en écoute');
    const hist=conversationState.historyByLife.get(life)||[];
    hist.push({role:'Vous',text});
    conversationState.historyByLife.set(life,hist);
    renderHistory(life);
    input.value='';
    setFlowState('en réflexion');
    await runAction('lives_use',{name:life});
    await runAction('talk',{prompt:text});
    hist.push({role:'Singular',text:'Réponse envoyée. Consultez les logs et résultats action pour le détail.'});
    conversationState.historyByLife.set(life,hist);
    setFlowState('en écoute');
    renderMeta(life);
  });
};

export const renderConversationsSection=payload=>{
  const rows=(Array.isArray(payload?.items)?payload.items:[]).map(item=>normalizeItem(item,'conversation'));
  const lives=new Map();
  for(const row of rows){
    const life=row.owner||row.title||'Vie inconnue';
    if(!lives.has(life)){lives.set(life,{status:row.status,last_update:row.last_update});}
    const hist=conversationState.historyByLife.get(life)||[];
    if(row.title){hist.push({role:'Système',text:`${row.title} · ${row.next_step}`});}
    conversationState.historyByLife.set(life,hist.slice(-12));
    conversationState.lastMetaByLife.set(life,{status:row.status,last_update:row.last_update});
  }

  const list=document.getElementById('conversation-life-list');
  if(list){
    list.innerHTML='';
    if(!lives.size){list.innerHTML="<li class='empty-state'>Aucune vie détectée.</li>";}
    for(const [life,meta] of lives.entries()){
      const li=document.createElement('li');
      const flow=inferFlow(meta);
      li.innerHTML=`<button type='button' class='filter-chip' data-life='${life}'>${life}</button> <span class='summary-pill ${FLOW_STYLES[flow]||'summary-muted'}'>${flow}</span>`;
      li.querySelector('button').addEventListener('click',()=>{
        conversationState.selectedLife=life;
        renderMeta(life);
      });
      list.appendChild(li);
    }
  }

  if(!conversationState.selectedLife&&lives.size){conversationState.selectedLife=[...lives.keys()][0];}
  renderMeta(conversationState.selectedLife);
  bindSend(rows);

  const raw=document.getElementById('conversations-json-raw');
  if(raw){raw.textContent=JSON.stringify(payload||{items:[]},null,2);}
  bindJsonToggle('conversations-json-toggle','conversations-json-raw');
};
