import {
  Crowd,
  NavMeshQuery,
  crowdAgentParamsDefaults,
  init as coreInit,
  statusToReadableString,
} from 'recast-navigation';
import {
  generateSoloNavMesh,
} from '@recast-navigation/generators';
import createWasmModule from '@recast-navigation/wasm/wasm-compat';

let initPromise = null;

async function init() {
  if (!initPromise) {
    initPromise = coreInit(() => createWasmModule()).then(() => true);
  }
  await initPromise;
  return api;
}

const api = {
  init,
  Crowd,
  NavMeshQuery,
  crowdAgentParamsDefaults,
  statusToReadableString,
  generateSoloNavMesh,
  version: '0.42.0',
};

if (typeof window !== 'undefined') {
  window.RecastNav = api;
}

export default api;
