const actionResultTargets=()=>[
  document.getElementById('action-result'),
  document.getElementById('critical-action-result'),
].filter(Boolean);

const writeActionResult=text=>{
  actionResultTargets().forEach(target=>{target.textContent=text;});
};

const readValue=(...ids)=>{
  for(const id of ids){
    const value=document.getElementById(id)?.value?.trim();
    if(value){return value;}
  }
  return '';
};

const operatorLifeSelect=()=>document.getElementById('operator-action-life-select');
const selectedOperatorLife=()=>readValue('operator-action-life-select','action-life-name');
const operatorMessage=()=>readValue('operator-action-message','action-prompt');
const birthName=()=>readValue('operator-birth-name','action-life-name');

const validOperatorLives=()=>{
  const select=operatorLifeSelect();
  if(!select){return new Set();}
  return new Set([...select.options].map(option=>option.value).filter(Boolean));
};

const hasValidSelectedLife=()=>{
  const selected=operatorLifeSelect()?.value?.trim()||'';
  if(!selected){return false;}
  const lives=validOperatorLives();
  return lives.size===0?false:lives.has(selected);
};

const setActionHelp=text=>{
  const help=document.getElementById('operator-action-help');
  if(help){help.textContent=text;}
  if(text){writeActionResult(text);}
};

const requiresValidLife=action=>['archive','talk'].includes(action);

export const updateOperatorActionState=()=>{
  const hasSelection=hasValidSelectedLife();
  const select=operatorLifeSelect();
  const selected=select?.value?.trim()||'';
  const help=document.getElementById('operator-action-help');
  const helpText=hasSelection
    ? `Vie ciblée: ${selected}. “Supprimer/archiver” et “Parler” sont disponibles.`
    : 'Sélectionnez une vie existante pour activer “Supprimer/archiver” et “Parler”.';
  if(help){help.textContent=helpText;}
  ['critical-archive','critical-talk','act-archive','act-talk'].forEach(id=>{
    const button=document.getElementById(id);
    if(!button){return;}
    button.disabled=false;
    button.classList.toggle('is-disabled',!hasSelection);
    button.setAttribute('aria-disabled',hasSelection?'false':'true');
    button.title=hasSelection?'':helpText;
  });
};

export const updateOperatorLifeOptions=(rows=[])=>{
  const select=operatorLifeSelect();
  if(!select){return;}
  const previous=select.value;
  const names=[...new Set((rows||[]).map(row=>{
    if(typeof row==='string'){return row;}
    return row?.life||row?.slug||row?.name||'';
  }).map(name=>String(name||'').trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
  select.innerHTML='';
  const placeholder=document.createElement('option');
  placeholder.value='';
  placeholder.textContent=names.length?'Sélectionner une vie existante…':'Aucune vie disponible';
  select.appendChild(placeholder);
  for(const name of names){
    const option=document.createElement('option');
    option.value=name;
    option.textContent=name;
    select.appendChild(option);
  }
  if(previous&&names.includes(previous)){select.value=previous;}
  else{
    const selectedRow=(rows||[]).find(row=>row?.selected_life===true||row?.active===true||row?.is_registry_active_life===true);
    const selectedName=selectedRow?.life||selectedRow?.slug||selectedRow?.name||'';
    if(selectedName&&names.includes(selectedName)){select.value=selectedName;}
  }
  updateOperatorActionState();
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

const actionPayload=(action,lifeName=selectedOperatorLife)=>{
  if(action==='birth'){return {name:birthName()};}
  if(action==='talk'){return {name:lifeName(),prompt:operatorMessage()};}
  if(action==='archive'){return {name:lifeName()};}
  if(action==='emergency_stop'){return {scope:'active_life'};}
  return {};
};

const validateAction=(action,payload)=>{
  if(requiresValidLife(action)&&!hasValidSelectedLife()){
    return 'Sélectionnez une vie valide dans le sélecteur opérateur avant de lancer cette action.';
  }
  if(action==='talk'&&!payload.prompt){
    return 'Écrivez un message dans le champ “Parler à une vie” avant d’envoyer.';
  }
  if(action==='birth'&&!payload.name){
    return 'Saisissez le nom exact de la vie à créer avant de confirmer la création.';
  }
  return '';
};

const confirmBirth=payload=>window.confirm(`Créer la vie nommée exactement “${payload.name}” ?`);

const confirmCriticalAction=button=>{
  const message=button.dataset.confirm;
  if(message&&!window.confirm(message)){return false;}
  const secondMessage=button.dataset.confirmAgain;
  if(secondMessage&&!window.confirm(secondMessage)){return false;}
  return true;
};

const runValidatedAction=(action,payload,handlers,button=null)=>{
  const help=validateAction(action,payload);
  if(help){setActionHelp(help);updateOperatorActionState();return false;}
  if(action==='birth'&&!confirmBirth(payload)){return false;}
  if(button&&!confirmCriticalAction(button)){return false;}
  return runAction(action,payload,handlers);
};

export const bindCriticalActionHandlers=(handlers)=>{
  const select=operatorLifeSelect();
  if(select&&select.dataset.bound!=='true'){
    select.dataset.bound='true';
    select.addEventListener('change',updateOperatorActionState);
  }
  ['operator-action-message','operator-birth-name','action-life-name','action-prompt'].forEach(id=>{
    const el=document.getElementById(id);
    if(el&&el.dataset.actionBound!=='true'){
      el.dataset.actionBound='true';
      el.addEventListener('input',updateOperatorActionState);
    }
  });
  updateOperatorActionState();
  document.querySelectorAll('.critical-actions-bar [data-dashboard-action]').forEach(button=>{
    if(button.offsetParent===null){return;}
    button.onclick=()=>{
      const action=button.dataset.dashboardAction||'';
      const payload=actionPayload(action,selectedOperatorLife);
      return runValidatedAction(action,payload,handlers,button);
    };
  });
};

export const bindActionHandlers=(handlers)=>{
  const lifeName=selectedOperatorLife;
  const prompt=operatorMessage;
  const budget=()=>Number(document.getElementById('action-budget')?.value||0);
  const bind=(id,handler)=>{
    const button=document.getElementById(id);
    if(button){button.onclick=handler;}
  };
  bind('act-birth',()=>runValidatedAction('birth',{name:birthName()},handlers));
  bind('act-talk',()=>runValidatedAction('talk',{name:lifeName(),prompt:prompt()},handlers));
  bind('act-loop',()=>runAction('loop',{budget_seconds:budget()},handlers));
  bind('act-report',()=>runAction('report',{},handlers));
  bind('act-lives-list',()=>runAction('lives_list',{},handlers));
  bind('act-lives-use',()=>runAction('lives_use',{name:lifeName()},handlers));
  bind('act-archive',()=>runValidatedAction('archive',{name:lifeName()},handlers));
  bind('act-memorial',()=>runAction('memorial',{name:lifeName(),message:'Merci pour ce cycle de vie.'},handlers));
  bind('act-clone',()=>runAction('clone',{name:lifeName(),new_name:`${lifeName()||'Vie'} clone`},handlers));
  bindCriticalActionHandlers(handlers);
};
