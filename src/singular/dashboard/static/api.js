import {scopeState} from './state.js';

export const withScope=(url)=>{
  const u=new URL(url,window.location.origin);
  if(scopeState.currentLifeOnly){u.searchParams.set('current_life_only','true');}
  return `${u.pathname}${u.search}`;
};

export const fetchJson=(url,options={})=>{
  const timeoutMs=options.timeoutMs??4500;
  const controller=new AbortController();
  const timeoutId=setTimeout(()=>controller.abort(),timeoutMs);
  return fetch(url,{...options,signal:controller.signal}).then(async response=>{
    if(!response.ok){throw new Error(`HTTP ${response.status} sur ${url}`);}
    return response.json();
  }).catch(error=>{
    if(error?.name==='AbortError'){
      const timeoutError=new Error(`Timeout API sur ${url}`);
      timeoutError.code='timeout';
      throw timeoutError;
    }
    throw error;
  }).finally(()=>clearTimeout(timeoutId));
};
