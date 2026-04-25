
// ─── BLOCK COLORS ───
const BLOCK_PALETTE = [
  { bg: 'rgba(0,229,255,0.15)', border: '#00e5ff', text: '#00e5ff' },
  { bg: 'rgba(255,107,53,0.15)', border: '#ff6b35', text: '#ff6b35' },
  { bg: 'rgba(127,255,110,0.15)', border: '#7fff6e', text: '#7fff6e' },
  { bg: 'rgba(255,215,0,0.15)', border: '#ffd700', text: '#ffd700' },
  { bg: 'rgba(200,100,255,0.15)', border: '#c864ff', text: '#c864ff' },
  { bg: 'rgba(255,165,0,0.15)', border: '#ffa500', text: '#ffa500' },
  { bg: 'rgba(255,82,82,0.15)', border: '#ff5252', text: '#ff5252' },
  { bg: 'rgba(100,210,255,0.15)', border: '#64d2ff', text: '#64d2ff' },
  { bg: 'rgba(255,200,120,0.15)', border: '#ffc878', text: '#ffc878' },
  { bg: 'rgba(120,200,120,0.15)', border: '#78c878', text: '#78c878' },
];

let blockColorMap = {};
let colorIndex = 0;

function getBlockColor(name) {
  if (!blockColorMap[name]) {
    blockColorMap[name] = BLOCK_PALETTE[colorIndex % BLOCK_PALETTE.length];
    colorIndex++;
  }
  return blockColorMap[name];
}

// ─── STATE ───
let planSteps = [];
let allStates = [];
let currentSimStep = 0;
let playInterval = null;
let isPlaying = false;

// ─── INIT DEFAULT STACKS ───
window.onload = () => {
  addStack('init', 'A B C');
  addStack('init', 'D E');
  addStack('goal', 'A');
  addStack('goal', 'B C D E');
  updateAlgoDesc();
  document.getElementById('algo-select').addEventListener('change', updateAlgoDesc);
};

function updateAlgoDesc() {
  const v = document.getElementById('algo-select').value;
  const desc = {
    bfs: '<strong>BFS</strong> — Guarantees the shortest plan. Explores all states level by level. Best for small-medium problems.',
    astar: '<strong>A*</strong> — Heuristic search using misplaced blocks + wrong-stack penalties. Faster than BFS for larger problems.',
    ids: '<strong>IDS</strong> — Iterative Deepening Search. Memory-efficient, finds optimal solution depth-first at increasing limits.'
  };
  document.getElementById('algo-desc').innerHTML = desc[v];
}

function switchTab(cfg, tab) {
  const tabs = document.querySelectorAll(`[id^="${cfg}-"] .tab, #${cfg}-text, #${cfg}-visual, #${cfg}-preset`);
  // Hide all content
  ['text','visual','preset'].forEach(t => {
    const el = document.getElementById(`${cfg}-${t}`);
    if (el) { el.classList.remove('active'); }
  });
  // Deactivate all tabs
  const panel = document.getElementById(`${cfg}-${tab}`).closest('.panel-body');
  panel.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  // Activate selected
  const tabEls = panel.querySelectorAll('.tab');
  const names = ['text','visual','preset'];
  const idx = names.indexOf(tab);
  if (tabEls[idx]) tabEls[idx].classList.add('active');
  const content = document.getElementById(`${cfg}-${tab}`);
  if (content) content.classList.add('active');
  if (tab === 'visual') updateVizPreview(cfg);
}

function updateVizPreview(cfg) {
  const stacks = readStacks(cfg);
  const container = document.getElementById(`${cfg}-viz-preview`);
  renderViz(stacks, container, false, []);
}

// ─── STACK MANAGER UI ───
function addStack(cfg, value = '') {
  const container = document.getElementById(`${cfg}-stacks`);
  const idx = container.children.length;
  const row = document.createElement('div');
  row.className = 'stack-row';
  const color = cfg === 'init' ? 'var(--accent)' : 'var(--accent2)';
  row.innerHTML = `
    <span class="stack-label">STACK ${idx+1}</span>
    <input type="text" class="stack-input" placeholder="e.g. A B C" value="${value}" 
      style="border-color:${color}20;" 
      onfocus="this.style.borderColor='${color}'"
      onblur="this.style.borderColor='${color}20'"
      oninput="onStackInput('${cfg}')">
    <button class="btn-remove-stack" onclick="removeStack(this, '${cfg}')">×</button>
  `;
  container.appendChild(row);
}

function removeStack(btn, cfg) {
  const row = btn.closest('.stack-row');
  row.remove();
  renumberStacks(cfg);
}

function renumberStacks(cfg) {
  const rows = document.querySelectorAll(`#${cfg}-stacks .stack-row`);
  rows.forEach((r, i) => { r.querySelector('.stack-label').textContent = `STACK ${i+1}`; });
}

function onStackInput(cfg) {
  // live update viz preview if on visual tab
}

function readStacks(cfg) {
  const inputs = document.querySelectorAll(`#${cfg}-stacks .stack-input`);
  const stacks = [];
  inputs.forEach(inp => {
    const val = inp.value.trim();
    if (val) {
      const blocks = val.split(/\s+/).filter(b => b.length > 0);
      if (blocks.length > 0) stacks.push(blocks);
    } else {
      stacks.push([]); // empty stack allowed
    }
  });
  return stacks.filter(s => s.length > 0); // remove empty
}

// ─── PRESETS ───
function loadPreset(val) {
  const presets = {
    simple: {
      init: [['A','B'],['C']],
      goal: [['C','B','A']]
    },
    medium: {
      init: [['A','B','C'],['D'],['E']],
      goal: [['E','D'],['C','B','A']]
    },
    complex: {
      init: [['A','B'],['C','D'],['E'],['F']],
      goal: [['F','E','D','C','B','A']]
    },
    tower: {
      init: [['A'],['B'],['C'],['D'],['E']],
      goal: [['A','B','C','D','E']]
    },
    shuffle: {
      init: [['D','C','B','A']],
      goal: [['A','B','C','D']]
    }
  };
  const p = presets[val];
  if (!p) return;
  blockColorMap = {}; colorIndex = 0;
  const initC = document.getElementById('init-stacks');
  const goalC = document.getElementById('goal-stacks');
  initC.innerHTML = ''; goalC.innerHTML = '';
  p.init.forEach(s => addStack('init', s.join(' ')));
  p.goal.forEach(s => addStack('goal', s.join(' ')));
}

// ─── PLANNING ALGORITHMS ───

// State: array of arrays (stacks), each stack bottom→top
function stateKey(state) {
  return state.map(s => s.join(',')).sort().join('|');
}

function getMoves(state) {
  const moves = [];
  for (let i = 0; i < state.length; i++) {
    if (state[i].length === 0) continue;
    for (let j = 0; j < state.length; j++) {
      if (i === j) continue;
      moves.push({ from: i, to: j });
    }
    // Also move to a new empty stack (represents floor)
    moves.push({ from: i, to: -1 }); // -1 = new stack
  }
  return moves;
}

function applyMove(state, move) {
  const newState = state.map(s => [...s]);
  const block = newState[move.from].pop();
  if (move.to === -1) {
    newState.push([block]);
  } else {
    newState[move.to].push(block);
  }
  // Remove empty stacks
  return newState.filter(s => s.length > 0);
}

function statesEqual(a, b) {
  return stateKey(a) === stateKey(b);
}

// Heuristic for A*: count blocks not in correct position
function heuristic(state, goal) {
  const goalKey = stateKey(goal);
  if (stateKey(state) === goalKey) return 0;
  
  // Build goal map: block -> {stack_idx, pos_in_stack}
  const goalPos = {};
  goal.forEach((stack, si) => {
    stack.forEach((block, pi) => {
      goalPos[block] = { stack: si, pos: pi, stackLen: stack.length };
    });
  });

  let h = 0;
  // For each block, check if it's in correct position with correct blocks below it
  state.forEach((stack, si) => {
    stack.forEach((block, pi) => {
      const gp = goalPos[block];
      if (!gp) { h += 2; return; }
      // Check if block below matches goal
      const goalStack = goal[gp.stack];
      const belowGoal = gp.pos > 0 ? goalStack[gp.pos - 1] : null;
      const belowCurrent = pi > 0 ? stack[pi - 1] : null;
      if (belowGoal !== belowCurrent) h++;
      if (pi !== gp.pos) h++;
    });
  });
  return h;
}

// BFS
function solveBFS(initState, goalState, maxSteps = 5000) {
  const start = initState.map(s => [...s]);
  if (statesEqual(start, goalState)) return [];
  
  const queue = [{ state: start, path: [] }];
  const visited = new Set();
  visited.add(stateKey(start));
  
  while (queue.length > 0) {
    if (visited.size > maxSteps) return null;
    const { state, path } = queue.shift();
    const moves = getMoves(state);
    for (const move of moves) {
      const newState = applyMove(state, move);
      const key = stateKey(newState);
      if (visited.has(key)) continue;
      visited.add(key);
      const block = state[move.from][state[move.from].length - 1];
      const fromName = `Stack${move.from + 1}`;
      const toName = move.to === -1 ? 'NewStack' : `Stack${move.to + 1}`;
      const newPath = [...path, { block, from: move.from, to: move.to, fromName, toName, state: newState }];
      if (statesEqual(newState, goalState)) return newPath;
      queue.push({ state: newState, path: newPath });
    }
  }
  return null;
}

// A* Search
function solveAStar(initState, goalState, maxSteps = 8000) {
  const start = initState.map(s => [...s]);
  if (statesEqual(start, goalState)) return [];
  
  // Priority queue (min-heap simulation)
  const open = [{ state: start, path: [], g: 0, f: heuristic(start, goalState) }];
  const visited = new Map();
  visited.set(stateKey(start), 0);
  
  let iters = 0;
  while (open.length > 0 && iters++ < maxSteps) {
    open.sort((a, b) => a.f - b.f);
    const { state, path, g } = open.shift();
    
    const moves = getMoves(state);
    for (const move of moves) {
      const newState = applyMove(state, move);
      const key = stateKey(newState);
      const newG = g + 1;
      if (visited.has(key) && visited.get(key) <= newG) continue;
      visited.set(key, newG);
      
      const block = state[move.from][state[move.from].length - 1];
      const fromName = `Stack${move.from + 1}`;
      const toName = move.to === -1 ? 'NewStack' : `Stack${move.to + 1}`;
      const newPath = [...path, { block, from: move.from, to: move.to, fromName, toName, state: newState }];
      
      if (statesEqual(newState, goalState)) return newPath;
      const h = heuristic(newState, goalState);
      open.push({ state: newState, path: newPath, g: newG, f: newG + h });
    }
  }
  return null;
}

// Iterative Deepening Search
function solveIDS(initState, goalState, maxDepth = 30) {
  const start = initState.map(s => [...s]);
  if (statesEqual(start, goalState)) return [];
  
  for (let limit = 1; limit <= maxDepth; limit++) {
    const result = dls(start, goalState, [], new Set([stateKey(start)]), limit);
    if (result !== null) return result;
  }
  return null;
}

function dls(state, goal, path, visited, limit) {
  if (statesEqual(state, goal)) return path;
  if (limit === 0) return undefined;
  
  const moves = getMoves(state);
  for (const move of moves) {
    const newState = applyMove(state, move);
    const key = stateKey(newState);
    if (visited.has(key)) continue;
    visited.add(key);
    const block = state[move.from][state[move.from].length - 1];
    const newPath = [...path, { block, from: move.from, to: move.to, state: newState }];
    const result = dls(newState, goal, newPath, visited, limit - 1);
    visited.delete(key);
    if (result !== undefined) return result;
  }
  return undefined;
}

// ─── VISUALIZATION ───
function renderViz(stacks, container, animate, highlightBlocks = []) {
  container.innerHTML = '';
  if (!stacks || stacks.length === 0) {
    container.innerHTML = '<div class="empty-msg">[ EMPTY STATE ]</div>';
    return;
  }
  stacks.forEach((stack, si) => {
    const col = document.createElement('div');
    col.className = 'stack-viz';
    
    const floor = document.createElement('div');
    floor.className = 'stack-floor';
    col.appendChild(floor);
    
    stack.forEach((block, bi) => {
      const c = getBlockColor(block);
      const div = document.createElement('div');
      div.className = 'block' + (highlightBlocks.includes(block) ? ' highlighted' : '');
      div.style.background = c.bg;
      div.style.borderColor = c.border;
      div.style.color = c.text;
      if (animate) div.style.animationDelay = `${bi * 0.05}s`;
      div.textContent = block;
      col.insertBefore(div, floor);
    });
    
    const label = document.createElement('div');
    label.className = 'stack-name';
    label.textContent = `S${si + 1}`;
    col.appendChild(label);
    container.appendChild(col);
  });
}

// ─── SOLVE MAIN ───
function solve() {
  const initStacks = readStacks('init');
  const goalStacks = readStacks('goal');
  
  if (initStacks.length === 0 || goalStacks.length === 0) {
    showAlert('error', 'ERROR: Please enter at least one stack for both configurations.');
    document.getElementById('results').style.display = 'block';
    return;
  }
  
  // Validate same blocks
  const initBlocks = initStacks.flat().sort();
  const goalBlocks = goalStacks.flat().sort();
  if (JSON.stringify(initBlocks) !== JSON.stringify(goalBlocks)) {
    showAlert('error', `BLOCK MISMATCH: Initial has [${initBlocks.join(', ')}], Goal has [${goalBlocks.join(', ')}]. Both must contain identical blocks.`);
    document.getElementById('results').style.display = 'block';
    return;
  }
  
  // Assign colors
  blockColorMap = {}; colorIndex = 0;
  initBlocks.forEach(b => getBlockColor(b));
  
  const algo = document.getElementById('algo-select').value;
  let plan;
  try {
    if (algo === 'bfs') plan = solveBFS(initStacks, goalStacks);
    else if (algo === 'astar') plan = solveAStar(initStacks, goalStacks);
    else plan = solveIDS(initStacks, goalStacks);
  } catch(e) {
    plan = null;
  }
  
  document.getElementById('results').style.display = 'block';
  
  // Render initial and goal
  renderViz(initStacks, document.getElementById('initial-viz'), true, []);
  renderViz(goalStacks, document.getElementById('goal-viz'), true, []);
  
  if (!plan) {
    showAlert('error', `NO SOLUTION FOUND. The problem may be too complex for this search limit, or the configurations are unreachable.`);
    document.getElementById('plan-output').innerHTML = '<div class="empty-msg">⚠ NO PLAN GENERATED</div>';
    return;
  }
  
  if (plan.length === 0) {
    showAlert('success', '✓ ALREADY AT GOAL STATE — No moves required!');
    document.getElementById('plan-output').innerHTML = '<div class="empty-msg">[ NO MOVES NEEDED ]</div>';
    renderViz(goalStacks, document.getElementById('final-viz'), true, []);
    document.getElementById('final-label').innerHTML = '<span style="color:var(--accent3)">✓ GOAL STATE ACHIEVED — 0 MOVES</span>';
    return;
  }
  
  planSteps = plan;
  allStates = [initStacks, ...plan.map(p => p.state)];
  currentSimStep = 0;
  
  // Stats
  const algoNames = { bfs:'BFS', astar:'A*', ids:'IDS' };
  document.getElementById('stats-row').innerHTML = `
    <div class="stat-chip">ALGORITHM<span>${algoNames[algo]}</span></div>
    <div class="stat-chip">TOTAL MOVES<span>${plan.length}</span></div>
    <div class="stat-chip">BLOCKS<span>${initBlocks.length}</span></div>
    <div class="stat-chip green">STATUS<span>SOLVED ✓</span></div>
  `;
  
  showAlert('success', `✓ PLAN FOUND — ${plan.length} move${plan.length === 1 ? '' : 's'} required using ${algoNames[algo]} search.`);
  
  // Render plan steps
  const planOut = document.getElementById('plan-output');
  planOut.innerHTML = '';
  const progressBar = document.getElementById('progress-bar');
  progressBar.style.display = 'block';
  document.getElementById('progress-fill').style.width = '100%';
  
  plan.forEach((step, i) => {
    const div = document.createElement('div');
    div.className = 'plan-step';
    div.style.animationDelay = `${i * 0.05}s`;
    const fromLabel = step.from >= 0 ? `Stack ${step.from + 1}` : '?';
    const toLabel = step.to === -1 ? 'New Stack' : `Stack ${step.to + 1}`;
    const stateStr = step.state.map((s, si) => `S${si+1}:[${s.join('→')}]`).join(' ');
    div.innerHTML = `
      <div class="step-num">[${String(i+1).padStart(2,'0')}]</div>
      <div class="step-icon">📦</div>
      <div class="step-text">
        MOVE <strong>${step.block}</strong> 
        FROM <span class="src">${fromLabel}</span> 
        TO <span class="dst">${toLabel}</span>
        <div class="step-state">→ ${stateStr}</div>
      </div>
    `;
    div.addEventListener('click', () => gotoStep(i + 1));
    div.style.cursor = 'pointer';
    planOut.appendChild(div);
  });
  
  // Simulator
  renderSimStep(0);
  document.getElementById('step-counter').textContent = `0 / ${plan.length}`;
  
  // Final state
  const finalState = plan[plan.length - 1].state;
  renderViz(finalState, document.getElementById('final-viz'), true, []);
  const match = statesEqual(finalState, goalStacks);
  document.getElementById('final-label').innerHTML = match
    ? '<span style="color:var(--accent3)">✓ GOAL STATE ACHIEVED — MISSION COMPLETE</span>'
    : '<span style="color:var(--danger)">⚠ FINAL STATE DIFFERS FROM GOAL</span>';
  
  // Scroll to results
  setTimeout(() => document.getElementById('results').scrollIntoView({ behavior: 'smooth' }), 100);
}

function showAlert(type, msg) {
  document.getElementById('alert-box').innerHTML = `<div class="alert ${type}">${msg}</div>`;
}

// ─── SIMULATOR ───
function renderSimStep(stepIdx) {
  const state = allStates[stepIdx];
  const container = document.getElementById('sim-viz');
  const highlight = stepIdx > 0 ? [planSteps[stepIdx - 1].block] : [];
  renderViz(state, container, true, highlight);
  
  if (stepIdx === 0) {
    document.getElementById('sim-state-label').textContent = 'STATE: INITIAL';
    document.getElementById('sim-action-label').textContent = '';
  } else {
    const s = planSteps[stepIdx - 1];
    const fromLabel = s.from >= 0 ? `Stack ${s.from + 1}` : '?';
    const toLabel = s.to === -1 ? 'New Stack' : `Stack ${s.to + 1}`;
    document.getElementById('sim-state-label').textContent = `STATE: AFTER MOVE ${stepIdx} / ${planSteps.length}`;
    document.getElementById('sim-action-label').textContent = `▶ Moved [${s.block}] from ${fromLabel} → ${toLabel}`;
  }
  
  currentSimStep = stepIdx;
  const total = planSteps.length;
  document.getElementById('step-counter').textContent = `${stepIdx} / ${total}`;
  const pct = total > 0 ? (stepIdx / total) * 100 : 0;
  document.getElementById('progress-fill2').style.width = pct + '%';
  
  // Highlight plan step
  document.querySelectorAll('.plan-step').forEach((el, i) => {
    el.style.background = (i === stepIdx - 1) ? 'rgba(127,255,110,0.05)' : '';
    el.style.borderLeft = (i === stepIdx - 1) ? '2px solid var(--accent3)' : '';
  });
  
  if (stepIdx > 0) {
    const planOut = document.getElementById('plan-output');
    const stepEl = planOut.children[stepIdx - 1];
    if (stepEl) stepEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function gotoStep(idx) {
  if (allStates.length === 0) return;
  if (idx === -1) idx = allStates.length - 1;
  idx = Math.max(0, Math.min(allStates.length - 1, idx));
  renderSimStep(idx);
}

function prevStep() { gotoStep(currentSimStep - 1); }
function nextStep() { gotoStep(currentSimStep + 1); }

function togglePlay() {
  if (isPlaying) {
    clearInterval(playInterval);
    isPlaying = false;
    document.getElementById('btn-play').textContent = '▶ PLAY';
  } else {
    if (currentSimStep >= allStates.length - 1) gotoStep(0);
    isPlaying = true;
    document.getElementById('btn-play').textContent = '⏸ PAUSE';
    const speed = parseInt(document.getElementById('anim-speed').value);
    playInterval = setInterval(() => {
      if (currentSimStep >= allStates.length - 1) {
        clearInterval(playInterval);
        isPlaying = false;
        document.getElementById('btn-play').textContent = '▶ PLAY';
      } else {
        nextStep();
      }
    }, speed);
  }
}

function resetAll() {
  if (isPlaying) { clearInterval(playInterval); isPlaying = false; }
  document.getElementById('results').style.display = 'none';
  planSteps = []; allStates = []; currentSimStep = 0;
  blockColorMap = {}; colorIndex = 0;
}
