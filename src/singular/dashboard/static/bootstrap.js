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
  schedulerTasks.set(name,{name,loader,intervalMs,nextRunAt:0,inFlight:false,errorCount:0,lastRunAt:null});
};

const runTask=async task=>{
  if(task.inFlight||schedulerState.paused){return;}
  task.inFlight=true;
  task.lastRunAt=Date.now();
  const binding=panelBindings[task.name];
  if(binding){setPanelState(binding.panelId,'loading','Chargement en cours…');}
  try{
    await task.loader();
    task.errorCount=0;
    task.nextRunAt=Date.now()+task.intervalMs;
    markUpdated(task.name,new Date());
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

const schedulerTick=()=>{
  if(schedulerState.paused){return;}
  const now=Date.now();
  for(const task of schedulerTasks.values()){if(task.nextRunAt<=now&&!task.inFlight){runTask(task);}}
};

const startScheduler=()=>{
  if(schedulerState.timer){clearInterval(schedulerState.timer);}
  schedulerState.timer=setInterval(schedulerTick,schedulerConfig.tickMs);
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

const toggleEssentialMode=()=>{
  document.body.classList.toggle('essential-mode');
  const btn=document.getElementById('toggle-essential');
  if(!btn){return;}
  const isEssential=document.body.classList.contains('essential-mode');
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
    localStorage.setItem(DASHBOARD_TAB_KEY,tabId);
    window.location.hash=selectedPaneId;
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
  if(essentialBtn){essentialBtn.onclick=toggleEssentialMode;}
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
  bindActionHandlers({onAfterAction:()=>Promise.all([loadEco(),loadCockpit(),loadTimeline()])});
  bindLivesHandlers(loadLivesBoard);
  bindLiveStreamHandlers();
  bindReflectionHandlers(loadReflections);
  bindCommonHandlers();

  registerTask('context',loadContext,schedulerConfig.frequencies.context);
  registerTask('retention',loadRetentionStatus,schedulerConfig.frequencies.retention);
  registerTask('ecosystem',loadEco,schedulerConfig.frequencies.ecosystem);
  registerTask('cockpit',loadCockpit,schedulerConfig.frequencies.cockpit);
  registerTask('timeline',loadTimeline,schedulerConfig.frequencies.timeline);
  registerTask('lives',loadLivesBoard,schedulerConfig.frequencies.lives);
  registerTask('genealogy',loadGenealogy,schedulerConfig.frequencies.genealogy);
  registerTask('quests',loadQuests,schedulerConfig.frequencies.quests);
  registerTask('hostVitals',loadHostVitals,schedulerConfig.frequencies.hostVitals);
  registerTask('reflections',loadReflections,schedulerConfig.frequencies.reflections);

  startScheduler();
  updateLiveStatus();

  ws.onmessage=e=>{
    const m=JSON.parse(e.data);
    if(m.type==='psyche'){document.getElementById('psyche').textContent=JSON.stringify(m.data,null,2);return;}
    if(m.type==='quests'){document.getElementById('quests').textContent=JSON.stringify(m.data,null,2);return;}
    if(typeof m.run_id==='string'&&typeof m.event==='string'){
      liveState.events.push({type:m.type,run_id:m.run_id,event:m.event,ts:m.ts||null});
      if(!liveState.paused){renderLiveEvents();}
    }
  };
};
