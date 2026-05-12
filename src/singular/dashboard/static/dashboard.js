import {bootstrapDashboard} from './bootstrap.js';

const writeBootstrapError=error=>{
  const message=`Erreur d’initialisation du dashboard: ${error?.message||'échec inconnu'}`;
  const target=document.getElementById('critical-action-result');
  if(target){target.textContent=message;return;}
  const banner=document.createElement('div');
  banner.className='critical-action-result';
  banner.setAttribute('role','alert');
  banner.textContent=message;
  document.body?.prepend(banner);
};

try{
  bootstrapDashboard();
}catch(error){
  writeBootstrapError(error);
  console.error('Dashboard bootstrap failed',error);
}

const parseFloatSafe=value=>{
  const match=String(value||'').replace(',', '.').match(/-?\d+(\.\d+)?/);
  return match?Number(match[0]):null;
};

const setActionableTone=(el,tone)=>{
  if(!el){return;}
  el.classList.remove('actionable-warn','actionable-critical');
  el.dataset.actionable='off';
  if(tone==='critical'){
    el.classList.add('actionable-critical');
    el.dataset.actionable='on';
  }
};

const isUrgencyText=text=>{
  const content=String(text||'').toLowerCase();
  return content.includes('critique')||content.includes('critical')||content.includes('urgence')||content.includes('emergency');
};

const updateDailyNarrativeSummary=()=>{
  const summaryList=document.getElementById('daily-autonomous-summary');
  if(!summaryList){return;}

  const healthText=document.getElementById('kpi-health')?.textContent?.trim()||'non disponible';
  const activeLivesText=document.getElementById('kpi-active-lives')?.textContent?.trim()||'0';
  const alertsText=document.getElementById('kpi-alerts')?.textContent?.trim()||'0';
  const trendText=document.getElementById('kpi-trend')?.textContent?.trim()||'non disponible';
  const riskText=document.getElementById('kpi-vital-risk')?.textContent?.trim()||'';

  const alertsValue=parseFloatSafe(alertsText)||0;
  const items=[
    `Autonomie observée: ${healthText}.`,
    `Stabilité collective: ${activeLivesText} vies actives suivies aujourd’hui.`,
    `La tendance récente est ${trendText}.`,
    alertsValue>0
      ? `${alertsText} incidents critiques ont été enregistrés sans intervention humaine.`
      : 'Aucun incident critique détecté sur la période observée.'
  ];

  if(isUrgencyText(riskText) || alertsValue>=3){
    items.push(`🚨 Urgence humaine requise: ${riskText||'un signal critique demande une validation humaine immédiate.'}`);
  }

  summaryList.innerHTML='';
  items.forEach(line=>{
    const li=document.createElement('li');
    const urgent=line.startsWith('🚨');
    li.textContent=line;
    if(urgent){
      li.classList.add('actionable-critical');
      li.dataset.humanRequired='true';
      li.setAttribute('aria-label','Urgence humaine requise');
    }
    summaryList.appendChild(li);
  });
};

const evaluateActionableSignals=()=>{
  const alertsEl=document.getElementById('kpi-alerts');
  const riskEl=document.getElementById('kpi-vital-risk');

  const alerts=parseFloatSafe(alertsEl?.textContent);
  if(alerts!==null&&alerts>=3){setActionableTone(alertsEl,'critical');}
  else{setActionableTone(alertsEl,null);}

  if(isUrgencyText(riskEl?.textContent)){ setActionableTone(riskEl,'critical'); }
  else{ setActionableTone(riskEl,null); }

  ['kpi-health','kpi-next-action','kpi-trend','kpi-autonomy-stability'].forEach(id=>setActionableTone(document.getElementById(id),null));
  updateDailyNarrativeSummary();
};

const bindSeeMoreToggles=()=>{
  document.querySelectorAll('[data-expand-target]').forEach(button=>{
    if(button.dataset.bound==='true'){return;}
    button.dataset.bound='true';
    button.addEventListener('click',()=>{
      const targetId=button.getAttribute('data-expand-target');
      const target=targetId?document.getElementById(targetId):null;
      if(!target){return;}
      const openLabel=button.dataset.openLabel||'Voir moins';
      const closedLabel=button.dataset.closedLabel||'Voir plus';
      const willOpen=target.classList.contains('panel-hidden');
      target.classList.toggle('panel-hidden',!willOpen);
      button.textContent=willOpen?openLabel:closedLabel;
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
