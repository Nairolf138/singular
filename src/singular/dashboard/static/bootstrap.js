import {bindActionHandlers} from './actions.js';
import {loadCockpit,loadContext,loadEco,loadHostVitals,loadQuests,loadRetentionStatus} from './render-cockpit.js';
import {bindLivesHandlers,bindLiveStreamHandlers,loadGenealogy,loadLivesBoard,renderLiveEvents,updateLiveStatus} from './render-lives.js';
import {bindReflectionHandlers,loadReflections} from './render-reflections.js';
import {loadTimeline} from './render-timeline.js';
import {
  PROLONGED_TIMEOUT_THRESHOLD,
  fmtTimestamp,
  liveState,
  markStaleTimeout,
  panelBindings,
  panelFirstLoadDone,
  schedulerConfig,
  schedulerLabelIds,
  schedulerState,
  schedulerTasks,
  scopeState,
  setPanelState,
} from './state.js';

const ws=new WebSocket(`ws://${location.host}/ws`);
const blockFreshness=new Map();
const ESSENTIAL_MODE_KEY='singular.dashboard.essentialMode';

const taskDefinitions={
  context:{loader:loadContext,intervalMs:schedulerConfig.frequencies.context,viewKey:'technique',blockId:'parametres',stream:'cold'},
  retention:{loader:loadRetentionStatus,intervalMs:schedulerConfig.frequencies.retention,viewKey:'decider-maintenant',blockId:'cockpit',stream:'cold'},
  ecosystem:{loader:loadEco,intervalMs:schedulerConfig.frequencies.ecosystem,viewKey:'technique',blockId:'parametres',stream:'cold'},
  cockpit:{loader:loadCockpit,intervalMs:schedulerConfig.frequencies.cockpit,viewKey:'decider-maintenant',blockId:'cockpit',stream:'hot'},
  timeline:{loader:loadTimeline,intervalMs:schedulerConfig.frequencies.timeline,viewKey:'diagnostiquer',blockId:'timeline-section',stream:'hot'},
  lives:{loader:loadLivesBoard,intervalMs:schedulerConfig.frequencies.lives,viewKey:'comparer-vies',blockId:'vies',stream:'cold'},
  genealogy:{loader:loadGenealogy,intervalMs:schedulerConfig.frequencies.genealogy,viewKey:'technique',blockId:'parametres',stream:'cold'},
  quests:{loader:loadQuests,intervalMs:schedulerConfig.frequencies.quests,viewKey:'technique',blockId:'parametres',stream:'cold'},
  hostVitals:{loader:loadHostVitals,intervalMs:schedulerConfig.frequencies.hostVitals,viewKey:'technique',blockId:'host-vitals-panel',stream:'cold'},
  reflections:{loader:loadReflections,intervalMs:schedulerConfig.frequencies.reflections,viewKey:'technique',blockId:'reflections-section',stream:'cold'},
};

const sectionIsVisible=blockId=>{
  const block=document.getElementById(blockId);
  if(!block){return false;}
  if(block.matches('details')&&!block.open){return false;}
  const pane=block.closest('.tab-pane');
  if(!pane){return true;}
  return !pane.classList.contains('panel-hidden');
};

const taskCanRun=task=>{
  if(document.visibilityState!=='visible'){return false;}
  if(schedulerState.pausedViews.has(task.viewKey)){return false;}
  if(task.viewKey!==schedulerState.activeTab){return false;}
  return sectionIsVisible(task.blockId);
};

const ensureUpdateLabel=(taskName)=>{
  const hostSection=document.getElementById(schedulerLabelIds[taskName]||'');
  if(!hostSection){return null;}
  const labelId=`last-update-${taskName}`;
  let label=document.getElementById(labelId);
  if(!label){
    label=document.createElement('div');
    label.id=labelId;
    label.className='status-muted';
    label.textContent='Dernière mise à jour: jamais';
    hostSection.appendChild(label);
  }
  return label;
};

const ensureFreshnessLabel=blockId=>{
  const hostSection=document.getElementById(blockId||'');
  if(!hostSection){return null;}
  const labelId=`freshness-${blockId}`;
  let label=document.getElementById(labelId);
  if(!label){
    label=document.createElement('div');
    label.id=labelId;
    label.className='status-muted';
    label.dataset.freshness='true';
    label.textContent='Mis à jour il y a jamais';
    hostSection.appendChild(label);
  }
  return label;
};

const updateFreshnessLabels=()=>{
  for(const [blockId,at] of blockFreshness.entries()){
    const label=ensureFreshnessLabel(blockId);
    if(!label){continue;}
    const elapsed=Math.max(0,Math.floor((Date.now()-at)/1000));
    label.textContent=`Mis à jour il y a ${elapsed}s`;
  }
};

const markBlockUpdated=(blockId,at)=>{
  if(!blockId){return;}
  blockFreshness.set(blockId,at);
  updateFreshnessLabels();
};

const markUpdated=(taskName,at)=>{
  const label=ensureUpdateLabel(taskName);
  if(label){label.textContent=`Dernière mise à jour (${taskName}): ${fmtTimestamp(at)}`;}
};

const markUpdateError=(taskName,error)=>{
  const label=ensureUpdateLabel(taskName);
  if(label){label.textContent=`Dernière mise à jour (${taskName}): erreur · ${error?.message||'échec réseau/API'}`;}
};

const shouldBackoff=(error)=>Boolean(error);

const registerTask=(name,loader,intervalMs)=>{
  const definition=taskDefinitions[name];
  schedulerTasks.set(name,{
    name,
    loader,
    intervalMs,
    nextRunAt:0,
    inFlight:false,
    errorCount:0,
    lastRunAt:null,
    stream:definition?.stream||'cold',
    viewKey:definition?.viewKey||'decider-maintenant',
    blockId:definition?.blockId||schedulerLabelIds[name]||'',
  });
};

const runTask=async task=>{
  if(task.inFlight||schedulerState.paused||!taskCanRun(task)){return;}
  task.inFlight=true;
  task.lastRunAt=Date.now();
  const binding=panelBindings[task.name];
  if(binding){setPanelState(binding.panelId,'loading','Chargement en cours…');}
  try{
    await task.loader();
    task.errorCount=0;
    task.nextRunAt=Date.now()+task.intervalMs;
    markUpdated(task.name,new Date());
    markBlockUpdated(task.blockId,Date.now());
    if(binding){
      const layer=document.getElementById(binding.panelId)?.querySelector(':scope > .state-layer');
      if(!layer||layer.dataset.state==='loading'){setPanelState(binding.panelId,'ready');}
      panelFirstLoadDone.add(binding.panelId);
    }
    markStaleTimeout(task.name,false);
  }catch(error){
    if(shouldBackoff(error)){
      task.errorCount+=1;
      const factor=schedulerConfig.backoff.multiplier**(task.errorCount-1);
      const retryIn=Math.min(schedulerConfig.backoff.maxMs,schedulerConfig.backoff.baseMs*factor);
      task.nextRunAt=Date.now()+retryIn;
      markUpdateError(task.name,error);
      if(binding){setPanelState(binding.panelId,'error',`API indisponible, nouvelle tentative dans ${Math.ceil(retryIn/1000)}s.`);} 
      markStaleTimeout(task.name,error?.code==='timeout'&&task.errorCount>=PROLONGED_TIMEOUT_THRESHOLD);
    }else{task.nextRunAt=Date.now()+task.intervalMs;}
  }finally{task.inFlight=false;}
};

const inflightCount=()=>[...schedulerTasks.values()].filter(task=>task.inFlight).length;

const schedulerTick=()=>{
  if(schedulerState.paused||document.visibilityState!=='visible'){return;}
  const now=Date.now();
  const slotsAvailable=Math.max(0,schedulerState.maxConcurrent-inflightCount());
  if(!slotsAvailable){return;}
  const dueTasks=[...schedulerTasks.values()]
    .filter(task=>task.nextRunAt<=now&&!task.inFlight&&taskCanRun(task))
    .sort((a,b)=>{
      if(a.stream!==b.stream){return a.stream==='hot'?-1:1;}
      return a.nextRunAt-b.nextRunAt;
    });
  dueTasks.slice(0,slotsAvailable).forEach(task=>runTask(task));
};

const startScheduler=()=>{
  if(schedulerState.timer){clearInterval(schedulerState.timer);}
  if(schedulerState.freshnessTimer){clearInterval(schedulerState.freshnessTimer);}
  schedulerState.timer=setInterval(schedulerTick,schedulerConfig.tickMs);
  schedulerState.freshnessTimer=setInterval(updateFreshnessLabels,1000);
  schedulerTick();
};

const toggleSchedulerPause=()=>{
  schedulerState.paused=!schedulerState.paused;
  const status=document.getElementById('updates-status');
  const button=document.getElementById('updates-toggle');
  if(status){status.textContent=schedulerState.paused?'Mises à jour globales: pause':'Mises à jour globales: actives';}
  if(button){button.textContent=schedulerState.paused?'Reprendre les mises à jour':'Pause updates';}
};

const bootstrapPauseControls=()=>{
  const section=document.getElementById('parametres');
  if(!section){return;}
  const wrap=document.createElement('div');
  wrap.className='panel';
  wrap.innerHTML="<h3 class='heading-reset-top'>Contrôle des mises à jour</h3><div id='updates-status'>Mises à jour globales: actives</div><button id='updates-toggle' type='button'>Pause updates</button>";
  section.prepend(wrap);
  document.getElementById('updates-toggle').onclick=toggleSchedulerPause;
};

const toggleViewPause=viewKey=>{
  if(schedulerState.pausedViews.has(viewKey)){schedulerState.pausedViews.delete(viewKey);}
  else{schedulerState.pausedViews.add(viewKey);}
  const status=document.getElementById(`updates-status-${viewKey}`);
  const button=document.getElementById(`updates-toggle-${viewKey}`);
  const isPaused=schedulerState.pausedViews.has(viewKey);
  if(status){status.textContent=isPaused?'Mises à jour de la vue: pause':'Mises à jour de la vue: actives';}
  if(button){button.textContent=isPaused?'Reprendre la vue':'Pause updates (vue)';}
};

const bootstrapViewPauseControls=()=>{
  document.querySelectorAll('.tab-pane').forEach(pane=>{
    const viewKey=(pane.id||'').replace('tab-','');
    if(!viewKey){return;}
    const wrap=document.createElement('div');
    wrap.className='panel';
    wrap.innerHTML=`<h3 class='heading-reset-top'>Contrôle de la vue</h3><div id='updates-status-${viewKey}'>Mises à jour de la vue: actives</div><button id='updates-toggle-${viewKey}' type='button'>Pause updates (vue)</button>`;
    pane.prepend(wrap);
    const button=wrap.querySelector(`#updates-toggle-${viewKey}`);
    if(button){button.onclick=()=>toggleViewPause(viewKey);}
  });
};

const applyEssentialVisibility=isEssential=>{
  document.body.classList.toggle('essential-mode',isEssential);
  document.querySelectorAll('[data-essential-level]').forEach(node=>{
    const level=Number(node.getAttribute('data-essential-level')||'1');
    const shouldHide=isEssential&&level>=3;
    if(node.tagName==='DETAILS'&&level===2){
      node.open=!isEssential;
    }
    if(level>=3){
      node.classList.toggle('panel-hidden',shouldHide);
    }
    node.setAttribute('aria-hidden',shouldHide?'true':'false');
  });
};

const toggleEssentialMode=()=>{
  const isEssential=!document.body.classList.contains('essential-mode');
  applyEssentialVisibility(isEssential);
  localStorage.setItem(ESSENTIAL_MODE_KEY,isEssential?'1':'0');
  const btn=document.getElementById('toggle-essential');
  if(!btn){return;}
  btn.textContent=`Mode Essentiel : ${isEssential?'ON':'OFF'}`;
  btn.setAttribute('aria-pressed',isEssential?'true':'false');
};

const DASHBOARD_TAB_KEY='singular.dashboard.lastTab';

const activateDashboardTab=tabId=>{
  const panes=document.querySelectorAll('.tab-pane');
  const triggers=document.querySelectorAll('.tab-trigger');
  if(!panes.length||!triggers.length){return;}
  const selectedPaneId=`tab-${tabId}`;
  let hasSelection=false;
  panes.forEach(pane=>{
    const isSelected=pane.id===selectedPaneId;
    pane.classList.toggle('panel-hidden',!isSelected);
    if(isSelected){hasSelection=true;}
  });
  triggers.forEach(trigger=>{
    const isSelected=hasSelection&&trigger.dataset.tab===tabId;
    trigger.setAttribute('aria-selected',isSelected?'true':'false');
    trigger.tabIndex=isSelected?0:-1;
  });
  if(hasSelection){
    schedulerState.activeTab=tabId;
    localStorage.setItem(DASHBOARD_TAB_KEY,tabId);
    window.location.hash=selectedPaneId;
    schedulerTick();
  }
};

const bindTabNavigation=()=>{
  const triggers=document.querySelectorAll('.tab-trigger');
  if(!triggers.length){return;}
  triggers.forEach(trigger=>{trigger.onclick=()=>activateDashboardTab(trigger.dataset.tab||'decider-maintenant');});
  const fromHash=(window.location.hash||'').replace('#tab-','');
  const fromStorage=localStorage.getItem(DASHBOARD_TAB_KEY)||'';
  activateDashboardTab(fromHash||fromStorage||'decider-maintenant');
};

const bindCommonHandlers=()=>{
  bindTabNavigation();
  const essentialBtn=document.getElementById('toggle-essential');
  const defaultEssential=localStorage.getItem(ESSENTIAL_MODE_KEY)==='1';
  applyEssentialVisibility(defaultEssential);
  if(essentialBtn){
    essentialBtn.textContent=`Mode Essentiel : ${defaultEssential?'ON':'OFF'}`;
    essentialBtn.setAttribute('aria-pressed',defaultEssential?'true':'false');
    essentialBtn.onclick=toggleEssentialMode;
  }
  const scopeToggle=document.getElementById('scope-current-life');
  if(scopeToggle){
    scopeToggle.onchange=e=>{
      scopeState.currentLifeOnly=Boolean(e.target.checked);
      loadCockpit();
      loadLivesBoard();
      loadTimeline();
      loadReflections();
    };
  }
};

export const bootstrapDashboard=()=>{
  bootstrapPauseControls();
  bootstrapViewPauseControls();
  bindActionHandlers({onAfterAction:()=>Promise.all([loadEco(),loadCockpit(),loadTimeline()])});
  bindLivesHandlers(loadLivesBoard);
  bindLiveStreamHandlers();
  bindReflectionHandlers(loadReflections);
  bindCommonHandlers();

  Object.entries(taskDefinitions).forEach(([name,definition])=>registerTask(name,definition.loader,definition.intervalMs));

  startScheduler();
  updateLiveStatus();

  ws.onmessage=e=>{
    const m=JSON.parse(e.data);
    if(m.type==='psyche'){document.getElementById('psyche').textContent=JSON.stringify(m.data,null,2);return;}
    if(m.type==='quests'){document.getElementById('quests').textContent=JSON.stringify(m.data,null,2);return;}
    if(['timeline','run_event','alert','alerts'].includes(m.type)){
      const task=schedulerTasks.get('timeline');
      if(task){task.nextRunAt=0;}
    }
    if(['alert','alerts','cockpit'].includes(m.type)){
      const task=schedulerTasks.get('cockpit');
      if(task){task.nextRunAt=0;}
    }
    if(typeof m.run_id==='string'&&typeof m.event==='string'){
      liveState.events.push({type:m.type,run_id:m.run_id,event:m.event,ts:m.ts||null});
      if(!liveState.paused){renderLiveEvents();}
    }
    schedulerTick();
  };
};
