import {bootstrapDashboard} from './bootstrap.js';

bootstrapDashboard();

const parseFloatSafe=value=>{
  const match=String(value||'').replace(',', '.').match(/-?\d+(\.\d+)?/);
  return match?Number(match[0]):null;
};

const setActionableTone=(el,tone)=>{
  if(!el){return;}
  el.classList.remove('actionable-warn','actionable-critical');
  el.dataset.actionable='off';
  if(tone==='warn'){
    el.classList.add('actionable-warn');
    el.dataset.actionable='on';
  }
  if(tone==='critical'){
    el.classList.add('actionable-critical');
    el.dataset.actionable='on';
  }
};

const evaluateActionableSignals=()=>{
  const expertMode=document.body?.dataset?.dashboardMode==='expert';
  const alertsEl=document.getElementById('kpi-alerts');
  const riskEl=document.getElementById('kpi-vital-risk');

  // Mode standard : uniquement alertes d’observation + état d’urgence.
  const alerts=parseFloatSafe(alertsEl?.textContent);
  if(alerts===null||alerts<=0){setActionableTone(alertsEl,null);}
  else if(alerts>=3){setActionableTone(alertsEl,'critical');}
  else{setActionableTone(alertsEl,'warn');}

  const riskText=String(riskEl?.textContent||'').toLowerCase();
  if(riskText.includes('critique')||riskText.includes('critical')||riskText.includes('urgence')||riskText.includes('emergency')){
    setActionableTone(riskEl,'critical');
  }else if(riskText.includes('élevé')||riskText.includes('high')||riskText.includes('warn')){
    setActionableTone(riskEl,'warn');
  }else{
    setActionableTone(riskEl,null);
  }

  if(!expertMode){
    ['kpi-health','kpi-next-action','kpi-trend','kpi-autonomy-stability'].forEach(id=>setActionableTone(document.getElementById(id),null));
    return;
  }

  // Mode expert : conservation des signaux avancés existants.
  const healthEl=document.getElementById('kpi-health');
  const trendEl=document.getElementById('kpi-trend');
  const autonomyStabilityEl=document.getElementById('kpi-autonomy-stability');
  const health=parseFloatSafe(healthEl?.textContent);
  if(health===null){setActionableTone(healthEl,null);}
  else if(health<40){setActionableTone(healthEl,'critical');}
  else if(health<65){setActionableTone(healthEl,'warn');}
  else{setActionableTone(healthEl,null);}

  const trendText=String(trendEl?.textContent||'').toLowerCase();
  if(trendText.includes('dégradation')||trendText.includes('degradation')){setActionableTone(trendEl,'warn');}
  else{setActionableTone(trendEl,null);}

  const stability=parseFloatSafe(autonomyStabilityEl?.textContent);
  if(stability===null){setActionableTone(autonomyStabilityEl,null);}
  else if(stability<50){setActionableTone(autonomyStabilityEl,'critical');}
  else if(stability<70){setActionableTone(autonomyStabilityEl,'warn');}
  else{setActionableTone(autonomyStabilityEl,null);}
};

const bindSeeMoreToggles=()=>{
  document.querySelectorAll('[data-expand-target]').forEach(button=>{
    button.addEventListener('click',()=>{
      const targetId=button.getAttribute('data-expand-target');
      const target=targetId?document.getElementById(targetId):null;
      if(!target){return;}
      const willOpen=target.classList.contains('panel-hidden');
      target.classList.toggle('panel-hidden',!willOpen);
      button.textContent=willOpen?'Voir moins':'Voir plus';
      button.setAttribute('aria-expanded',willOpen?'true':'false');
    });
  });
};

const bindSignalObserver=()=>{
  const cockpit=document.getElementById('cockpit');
  if(!cockpit){return;}
  evaluateActionableSignals();
  const observer=new MutationObserver(()=>evaluateActionableSignals());
  observer.observe(cockpit,{subtree:true,childList:true,characterData:true});
};

const initDashboardEnhancements=()=>{
  bindSeeMoreToggles();
  bindSignalObserver();
};

if(document.readyState==='loading'){
  document.addEventListener('DOMContentLoaded',initDashboardEnhancements,{once:true});
}else{
  initDashboardEnhancements();
}
