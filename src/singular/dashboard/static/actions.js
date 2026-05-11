const actionResultTargets=()=>[
  document.getElementById('action-result'),
  document.getElementById('critical-action-result'),
].filter(Boolean);

const writeActionResult=text=>{
  actionResultTargets().forEach(target=>{target.textContent=text;});
};

export const runAction=(action,payload,{onAfterAction}={})=>{
  const token=document.getElementById('action-token')?.value||'';
  const q=new URLSearchParams();
  if(token){q.set('token',token);}
  if(payload){q.set('payload',JSON.stringify(payload));}
  return fetch(`/api/actions/${action}?${q.toString()}`).then(async r=>{
    if(!r.ok){throw new Error(`HTTP ${r.status}`);}
    return r.json();
  }).then(async data=>{
    writeActionResult(JSON.stringify(data,null,2));
    if(typeof onAfterAction==='function'){await onAfterAction();}
  }).catch(err=>{
    writeActionResult(`Erreur action ${action}: ${err.message}`);
  });
};

const actionPayload=(action,lifeName)=>{
  if(action==='birth'){return {name:lifeName()||'Nouvelle vie'};}
  if(action==='talk'){return {prompt:document.getElementById('action-prompt')?.value||''};}
  if(action==='archive'){return {name:lifeName()};}
  if(action==='emergency_stop'){return {scope:'active_life'};}
  return {};
};

const confirmCriticalAction=button=>{
  const message=button.dataset.confirm;
  if(message&&!window.confirm(message)){return false;}
  const secondMessage=button.dataset.confirmAgain;
  if(secondMessage&&!window.confirm(secondMessage)){return false;}
  return true;
};

export const bindCriticalActionHandlers=(handlers)=>{
  const lifeName=()=>document.getElementById('action-life-name')?.value||'';
  document.querySelectorAll('.critical-actions-bar [data-dashboard-action]').forEach(button=>{
    if(button.offsetParent===null){return;}
    button.onclick=()=>{
      if(button.disabled||!confirmCriticalAction(button)){return false;}
      const action=button.dataset.dashboardAction||'';
      return runAction(action,actionPayload(action,lifeName),handlers);
    };
  });
};

export const bindActionHandlers=(handlers)=>{
  const lifeName=()=>document.getElementById('action-life-name').value||'';
  document.getElementById('act-birth').onclick=()=>runAction('birth',{name:lifeName()||'Nouvelle vie'},handlers);
  document.getElementById('act-talk').onclick=()=>runAction('talk',{prompt:document.getElementById('action-prompt').value||''},handlers);
  document.getElementById('act-loop').onclick=()=>runAction('loop',{budget_seconds:Number(document.getElementById('action-budget').value||0)},handlers);
  document.getElementById('act-report').onclick=()=>runAction('report',{},handlers);
  document.getElementById('act-lives-list').onclick=()=>runAction('lives_list',{},handlers);
  document.getElementById('act-lives-use').onclick=()=>runAction('lives_use',{name:lifeName()},handlers);
  document.getElementById('act-archive').onclick=()=>runAction('archive',{name:lifeName()},handlers);
  document.getElementById('act-memorial').onclick=()=>runAction('memorial',{name:lifeName(),message:'Merci pour ce cycle de vie.'},handlers);
  document.getElementById('act-clone').onclick=()=>runAction('clone',{name:lifeName(),new_name:`${lifeName()||'Vie'} clone`},handlers);
  bindCriticalActionHandlers(handlers);
};
