import {updateOperatorLifeOptions} from './actions.js';
import {normalizeItem} from './render-quests.js';
import {getSelectedLife,SELECTED_LIFE_CHANGED_EVENT,setSelectedLife} from './state.js';

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
  'archivée':'summary-critical',
  'run en cours':'summary-warning',
  'token manquant':'summary-critical',
  'erreur provider':'summary-critical',
  'arrêtée':'summary-critical',
};

const STATUS_LABELS={
  ok:'en écoute',
  life_unavailable:'indisponible',
  life_archived:'archivée',
  run_in_progress:'run en cours',
  token_missing:'token manquant',
  token_invalid:'token manquant',
  provider_error:'erreur provider',
  error:'indisponible',
  message_missing:'indisponible',
};

const setText=(id,text)=>{const el=document.getElementById(id);if(el){el.textContent=text;}return el;};

const escapeHtml=value=>String(value??'').replace(/[&<>'"]/g,char=>({
  '&':'&amp;',
  '<':'&lt;',
  '>':'&gt;',
  "'":'&#39;',
  '"':'&quot;',
}[char]));

const highlightConversationLife=(life)=>{
  document.querySelectorAll('#conversation-life-list [data-life]').forEach(node=>{
    const active=node.dataset.life===life;
    node.classList.toggle('active',active);
    node.setAttribute('aria-pressed',active?'true':'false');
  });
};

const syncConversationSelection=(life)=>{
  conversationState.selectedLife=life||'';
  highlightConversationLife(conversationState.selectedLife);
  renderMeta(conversationState.selectedLife);
};

let selectedLifeListenerBound=false;
const bindSelectedLifeListener=()=>{
  if(selectedLifeListenerBound||typeof window==='undefined'){return;}
  selectedLifeListenerBound=true;
  window.addEventListener(SELECTED_LIFE_CHANGED_EVENT,event=>{
    syncConversationSelection(event.detail?.name||'');
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
  const chatStatus=String(meta?.chat_status||'').toLowerCase();
  if(STATUS_LABELS[chatStatus]){return STATUS_LABELS[chatStatus];}
  const status=String(meta?.status||'').toLowerCase();
  if(status.includes('archiv')){return 'archivée';}
  if(status.includes('stop')||status.includes('dead')||status.includes('extinct')){return 'arrêtée';}
  if(status.includes('busy')||status.includes('thinking')||status.includes('processing')||status.includes('run')){return 'run en cours';}
  if(status.includes('available')||status.includes('ready')||status.includes('active')){return 'en écoute';}
  return 'indisponible';
};

const renderHistory=(life)=>{
  const historyEl=document.getElementById('conversation-history');
  if(!historyEl){return;}
  const history=conversationState.historyByLife.get(life)||[];
  if(!history.length){historyEl.textContent='Aucun message.';return;}
  historyEl.innerHTML=history.slice(-8).map(item=>`<div><strong>${escapeHtml(item.role)}:</strong> ${escapeHtml(item.text)}</div>`).join('');
};

const renderMeta=(life)=>{
  const meta=conversationState.lastMetaByLife.get(life)||{};
  setText('conversation-selected-life',`Vie: ${life||'aucune sélection'}`);
  setText('conversation-availability',`Disponibilité: ${meta.status||'inconnue'}`);
  setText('conversation-last-activity',`Activité récente: ${meta.last_update||meta.last_activity||'non disponible'}`);
  const history=conversationState.historyByLife.get(life)||[];
  const lastMsg=history.length?history[history.length-1].text:'aucun';
  setText('conversation-last-message',`Dernier message: ${lastMsg}`);
  setFlowState(inferFlow(meta));
  renderHistory(life);
};

const statusFromResponse=status=>STATUS_LABELS[String(status||'').toLowerCase()]||'indisponible';

const bindSend=()=>{
  const sendBtn=document.getElementById('conversation-send');
  const input=document.getElementById('conversation-input');
  if(!sendBtn||sendBtn.dataset.bound==='true'||!input){return;}
  sendBtn.dataset.bound='true';
  sendBtn.addEventListener('click',async ()=>{
    const life=conversationState.selectedLife;
    const text=input.value.trim();
    if(!life||!text){setFlowState('indisponible');return;}
    const hist=conversationState.historyByLife.get(life)||[];
    hist.push({role:'Vous',text});
    conversationState.historyByLife.set(life,hist);
    renderHistory(life);
    input.value='';
    setFlowState('en réflexion');
    sendBtn.disabled=true;
    const token=document.getElementById('action-token')?.value||'';
    const q=new URLSearchParams();
    if(token){q.set('token',token);}
    try{
      const response=await fetch(`/api/lives/${encodeURIComponent(life)}/chat?${q.toString()}`,{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message:text}),
      });
      const payload=await response.json();
      const reply=payload?.response||`Erreur HTTP ${response.status}`;
      hist.push({role:'Singular',text:reply});
      conversationState.historyByLife.set(life,hist);
      const previousMeta=conversationState.lastMetaByLife.get(life)||{};
      conversationState.lastMetaByLife.set(life,{
        ...previousMeta,
        chat_status:payload?.status||(!response.ok?'error':'ok'),
        status:payload?.status||previousMeta.status,
        last_update:payload?.timestamp||previousMeta.last_update,
      });
      setFlowState(statusFromResponse(payload?.status));
      renderMeta(life);
    }catch(err){
      hist.push({role:'Singular',text:`Erreur conversation: ${err.message}`});
      conversationState.historyByLife.set(life,hist);
      const previousMeta=conversationState.lastMetaByLife.get(life)||{};
      conversationState.lastMetaByLife.set(life,{...previousMeta,chat_status:'error'});
      setFlowState('indisponible');
      renderMeta(life);
    }finally{
      sendBtn.disabled=false;
    }
  });
};

const addLife=(lives,life,meta={})=>{
  if(!life){return;}
  const existing=lives.get(life)||{};
  lives.set(life,{...existing,...meta});
};

const collectLives=(payload,rows)=>{
  const lives=new Map();
  const ctxLives=Array.isArray(payload?.context?.registry_lives)?payload.context.registry_lives:[];
  for(const item of ctxLives){
    const life=item.slug||item.name;
    addLife(lives,life,{status:item.status,last_update:item.created_at,active:item.active});
  }
  const comparisonRows=Array.isArray(payload?.comparison?.table)?payload.comparison.table:[];
  for(const item of comparisonRows){
    const life=item.life||item.slug||item.name;
    addLife(lives,life,{status:item.registry_status||item.status||item.life_status,last_update:item.last_activity,selected_life:item.selected_life});
  }
  const comparisonLives=payload?.comparison?.lives||{};
  for(const [life,meta] of Object.entries(comparisonLives)){
    addLife(lives,life,{status:meta?.registry_status||meta?.status,last_update:meta?.last_activity});
  }
  for(const row of rows){
    const life=row.owner||row.life||row.title||'Vie inconnue';
    addLife(lives,life,{status:row.status,last_update:row.last_update});
    const hist=conversationState.historyByLife.get(life)||[];
    if(row.title){hist.push({role:'Système',text:`${row.title} · ${row.next_step}`});}
    conversationState.historyByLife.set(life,hist.slice(-12));
  }
  return lives;
};

export const renderConversationsSection=payload=>{
  const rows=(Array.isArray(payload?.items)?payload.items:[]).map(item=>normalizeItem(item,'conversation'));
  const lives=collectLives(payload||{},rows);
  for(const [life,meta] of lives.entries()){
    conversationState.lastMetaByLife.set(life,{...(conversationState.lastMetaByLife.get(life)||{}),...meta});
  }

  const list=document.getElementById('conversation-life-list');
  if(list){
    list.innerHTML='';
    if(!lives.size){list.innerHTML="<li class='empty-state'>Aucune vie détectée.</li>";}
    for(const [life,meta] of lives.entries()){
      const li=document.createElement('li');
      const flow=inferFlow(meta);
      li.innerHTML=`<button type='button' class='filter-chip' data-life='${escapeHtml(life)}'>${escapeHtml(life)}</button> <span class='summary-pill ${FLOW_STYLES[flow]||'summary-muted'}'>${escapeHtml(flow)}</span>`;
      li.querySelector('button').addEventListener('click',()=>{
        setSelectedLife(life,{source:'conversation-list',metadata:meta});
      });
      list.appendChild(li);
    }
  }

  const sharedLife=getSelectedLife();
  if(sharedLife&&lives.has(sharedLife)){conversationState.selectedLife=sharedLife;}
  if(!conversationState.selectedLife&&lives.size){
    const selected=[...lives.entries()].find(([,meta])=>meta.active||meta.selected_life);
    conversationState.selectedLife=selected?.[0]||[...lives.keys()][0];
    setSelectedLife(conversationState.selectedLife,{source:'conversation-default',metadata:lives.get(conversationState.selectedLife)||{}});
  }
  bindSelectedLifeListener();
  updateOperatorLifeOptions([...lives.entries()].map(([life,meta])=>({life,...meta})));
  syncConversationSelection(conversationState.selectedLife);
  bindSend();

  const raw=document.getElementById('conversations-json-raw');
  if(raw){raw.textContent=JSON.stringify(payload||{items:[]},null,2);}
};
