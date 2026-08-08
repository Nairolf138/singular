import {fetchJson,withScope} from './api.js';

const CACHE_TTL_MS=1500;
const cache=new Map();

const cachedJson=url=>{
  const now=Date.now();
  const cached=cache.get(url);
  if(cached&&now-cached.at<CACHE_TTL_MS){return cached.promise;}
  const promise=fetchJson(url).catch(error=>{
    cache.delete(url);
    throw error;
  });
  cache.set(url,{at:now,promise});
  return promise;
};

export const fetchSharedDashboardContext=()=>cachedJson('/dashboard/context');
export const fetchSharedLivesComparison=()=>cachedJson(withScope('/lives/comparison?sort_by=last_activity&sort_order=desc'));
export const fetchSharedCockpitEssential=()=>cachedJson(withScope('/api/cockpit/essential'));

export const fetchSharedDashboardData=()=>Promise.allSettled([
  fetchSharedDashboardContext(),
  fetchSharedLivesComparison(),
  fetchSharedCockpitEssential(),
]).then(results=>{
  const [contextResult,comparisonResult,essentialResult]=results;
  return {
    context:contextResult.status==='fulfilled'?contextResult.value:{},
    comparison:comparisonResult.status==='fulfilled'?comparisonResult.value:{table:[]},
    essential:essentialResult.status==='fulfilled'?essentialResult.value:{},
    registryState:results.every(result=>result.status==='rejected')?'error':(
      results.some(result=>result.status==='rejected')?'partial':'ready'
    ),
  };
});
