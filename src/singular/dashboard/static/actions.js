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
  const lifeName=()=>document.getElementById('action-life-name')?.value||'';
  const prompt=()=>document.getElementById('action-prompt')?.value||'';
  const budget=()=>Number(document.getElementById('action-budget')?.value||0);
  const bind=(id,handler)=>{
    const button=document.getElementById(id);
    if(button){button.onclick=handler;}
  };
  bind('act-birth',()=>runAction('birth',{name:lifeName()||'Nouvelle vie'},handlers));
  bind('act-talk',()=>runAction('talk',{prompt:prompt()},handlers));
  bind('act-loop',()=>runAction('loop',{budget_seconds:budget()},handlers));
  bind('act-report',()=>runAction('report',{},handlers));
  bind('act-lives-list',()=>runAction('lives_list',{},handlers));
  bind('act-lives-use',()=>runAction('lives_use',{name:lifeName()},handlers));
  bind('act-archive',()=>runAction('archive',{name:lifeName()},handlers));
  bind('act-memorial',()=>runAction('memorial',{name:lifeName(),message:'Merci pour ce cycle de vie.'},handlers));
  bind('act-clone',()=>runAction('clone',{name:lifeName(),new_name:`${lifeName()||'Vie'} clone`},handlers));
  bindCriticalActionHandlers(handlers);
};
