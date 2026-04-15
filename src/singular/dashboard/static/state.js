export const HOST_SENSORS_THRESHOLD={cpuWarn:85,cpuCritical:95,ramWarn:80,ramCritical:92,tempWarn:75,tempCritical:85,diskCritical:95};
export const BADGE_TONE={
  success:'badge-success',
  danger:'badge-danger',
  warning:'badge-warning',
  info:'badge-info',
};

export const MISSING_TEXT={notAvailable:'Non disponible',notMeasured:'Pas encore mesuré'};
export const na=()=>MISSING_TEXT.notAvailable;
export const nm=()=>MISSING_TEXT.notMeasured;

export const livesTableState={sortBy:'score',sortOrder:'desc'};
export const liveState={paused:false,autoScroll:true,events:[]};
export const scopeState={currentLifeOnly:false};
export const schedulerState={
  paused:false,
  timer:null,
  freshnessTimer:null,
  activeTab:'decider-maintenant',
  pausedViews:new Set(),
  maxConcurrent:2,
};
export const schedulerTasks=new Map();

export const schedulerConfig={
  tickMs:500,
  backoff:{baseMs:1500,maxMs:30000,multiplier:2},
  frequencies:{
    context:45000,
    retention:45000,
    cockpit:10000,
    ecosystem:30000,
    timeline:60000,
    lives:45000,
    reflections:30000,
    genealogy:45000,
    quests:45000,
    hostVitals:15000,
  },
};

export const schedulerLabelIds={
  context:'parametres',
  retention:'cockpit',
  cockpit:'cockpit',
  ecosystem:'cockpit',
  timeline:'timeline-section',
  lives:'vies',
  reflections:'reflections-section',
  genealogy:'vies',
  quests:'parametres',
  hostVitals:'cockpit',
};

export const panelBindings={
  cockpit:{panelId:'cockpit',emptyMessage:'Aucune donnée cockpit disponible.'},
  timeline:{panelId:'timeline-section',emptyMessage:'Aucun événement de timeline disponible.'},
  lives:{panelId:'vies',emptyMessage:'Aucune vie disponible pour les filtres actuels.'},
  reflections:{panelId:'reflections-section',emptyMessage:'Aucune réflexion pour ces filtres.'},
  hostVitals:{panelId:'host-vitals-panel',emptyMessage:'Aucune métrique hôte exploitable.'},
};

export const panelFirstLoadDone=new Set();
export const staleTimeoutTasks=new Set();
export const PROLONGED_TIMEOUT_THRESHOLD=2;

export const fmtTimestamp=(value=new Date())=>{
  const d=value instanceof Date?value:new Date(value);
  if(Number.isNaN(d.getTime())){return na();}
  return d.toLocaleString('fr-FR',{hour12:false});
};

export const setStatusTone=(el,tone)=>{
  el.classList.remove('status-good','status-warn','status-bad');
  if(tone==='good'){el.classList.add('status-good');}
  if(tone==='warn'){el.classList.add('status-warn');}
  if(tone==='bad'){el.classList.add('status-bad');}
};

export const applyStatusIndicator=(el,tone)=>{
  if(!el){return;}
  const icon=tone==='good'?'●':(tone==='warn'?'▲':(tone==='bad'?'■':'•'));
  el.classList.add('status-with-icon');
  el.dataset.statusIcon=icon;
};

export const ensurePanelLayer=(panelId)=>{
  const panel=document.getElementById(panelId);
  if(!panel){return null;}
  panel.classList.add('state-scope');
  let layer=panel.querySelector(':scope > .state-layer');
  if(!layer){
    layer=document.createElement('div');
    layer.className='state-layer';
    panel.insertBefore(layer,panel.firstChild);
  }
  return layer;
};

export const setPanelState=(panelId,state,message='')=>{
  const layer=ensurePanelLayer(panelId);
  if(!layer){return;}
  const defaultMessage=state==='loading'?'Chargement…':(state==='empty'?'Aucune donnée disponible.':(state==='error'?'Erreur de chargement.':''));
  layer.dataset.state=state;
  const text=message||defaultMessage;
  const withSkeleton=state==='loading'&&!panelFirstLoadDone.has(panelId);
  const skeleton=withSkeleton?"<div class='skeleton-line'></div><div class='skeleton-line'></div><div class='skeleton-line'></div>":'';
  layer.innerHTML=`<div class='state-message'>${text}</div>${skeleton}`;
  if(state==='ready'){layer.innerHTML='';}
};

export const updateStaleBanner=()=>{
  const banner=document.getElementById('stale-data-banner');
  if(!banner){return;}
  if(!staleTimeoutTasks.size){
    banner.classList.add('panel-hidden');
    banner.textContent='';
    return;
  }
  const tasks=[...staleTimeoutTasks].join(', ');
  banner.classList.remove('panel-hidden');
  banner.textContent=`⚠️ Données potentiellement obsolètes : timeout prolongé sur ${tasks}.`;
};

export const markStaleTimeout=(taskName,isTimeout)=>{
  if(isTimeout){staleTimeoutTasks.add(taskName);}else{staleTimeoutTasks.delete(taskName);}
  updateStaleBanner();
};
