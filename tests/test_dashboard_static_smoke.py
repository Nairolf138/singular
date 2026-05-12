from __future__ import annotations

import re
import subprocess
from pathlib import Path

DASHBOARD_STATIC = Path("src/singular/dashboard/static")
DASHBOARD_TEMPLATE = Path("src/singular/dashboard/templates/dashboard.html")
AUDITED_JS = [
    DASHBOARD_STATIC / "bootstrap.js",
    DASHBOARD_STATIC / "actions.js",
    DASHBOARD_STATIC / "render-cockpit.js",
    DASHBOARD_STATIC / "render-lives.js",
    DASHBOARD_STATIC / "render-conversations.js",
    DASHBOARD_STATIC / "render-reflections.js",
]


def _ids_declared_in(text: str) -> set[str]:
    return set(re.findall(r"\bid=[\"']([^\"']+)[\"']", text))


def test_dashboard_bootstrap_literal_ids_exist_or_are_created() -> None:
    """Smoke check: bootstrap literal DOM IDs are backed by dashboard HTML or injected controls."""
    html_ids = _ids_declared_in(DASHBOARD_TEMPLATE.read_text(encoding="utf-8"))
    bootstrap = (DASHBOARD_STATIC / "bootstrap.js").read_text(encoding="utf-8")
    bootstrap_created_ids = _ids_declared_in(bootstrap)
    literal_refs = set(
        re.findall(r"document\.getElementById\([\"']([A-Za-z0-9_-]+)[\"']\)", bootstrap)
    )

    missing = literal_refs - html_ids - bootstrap_created_ids
    unprotected_missing = {
        element_id
        for element_id in missing
        if re.search(rf"document\.getElementById\([\"']{re.escape(element_id)}[\"']\)\.", bootstrap)
    }
    assert not unprotected_missing, (
        "Bootstrap references missing dashboard IDs without a guard: "
        f"{sorted(unprotected_missing)}"
    )


def test_dashboard_js_uses_guards_for_direct_get_element_access() -> None:
    """Smoke check: direct getElementById(...).property writes are replaced by guarded variables/helpers."""
    offenders: list[str] = []
    direct_access = re.compile(r"document\.getElementById\([^\n]+?\)\.(?!\?)")
    for path in AUDITED_JS:
      text = path.read_text(encoding="utf-8")
      for match in direct_access.finditer(text):
          line = text.count("\n", 0, match.start()) + 1
          offenders.append(f"{path}:{line}: {match.group(0)}")

    assert not offenders, "Unprotected direct DOM access remains:\n" + "\n".join(offenders)


def test_dashboard_quests_websocket_targets_existing_raw_panel() -> None:
    bootstrap = (DASHBOARD_STATIC / "bootstrap.js").read_text(encoding="utf-8")
    assert "getElementById('quests')" not in bootstrap
    assert "getElementById('quests-json-raw')" in bootstrap or "loadQuests()" in bootstrap


def test_genealogy_renderer_escapes_malicious_life_names(tmp_path: Path) -> None:
    """Exercise the genealogy DOM renderer with a life name that looks like XSS."""
    script = tmp_path / "genealogy_escape_check.mjs"
    module_path = (Path.cwd() / DASHBOARD_STATIC / "render-lives.js").as_uri()
    script.write_text(
        f"""
const encode = value => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

class Element {{
  constructor(tagName) {{
    this.tagName = tagName;
    this.children = [];
    this.attributes = {{}};
    this.dataset = {{}};
    this._textContent = '';
    this._innerHTML = null;
    this.value = '';
    this.onchange = null;
  }}
  appendChild(child) {{
    this.children.push(child);
    this._innerHTML = null;
    return child;
  }}
  replaceChildren(...children) {{
    this.children = [];
    this._textContent = '';
    this._innerHTML = null;
    for (const child of children) {{ this.appendChild(child); }}
  }}
  set textContent(value) {{
    this._textContent = String(value ?? '');
    this.children = [];
    this._innerHTML = null;
  }}
  get textContent() {{
    return this._textContent + this.children.map(child => child.textContent ?? '').join('');
  }}
  set innerHTML(value) {{
    this._innerHTML = String(value ?? '');
    this.children = [];
    this._textContent = '';
  }}
  get innerHTML() {{
    if (this._innerHTML !== null) {{ return this._innerHTML; }}
    return encode(this._textContent) + this.children.map(child => child.outerHTML ?? encode(child.textContent ?? '')).join('');
  }}
  set colSpan(value) {{ this.attributes.colspan = String(value); }}
  set className(value) {{ this.attributes.class = String(value); }}
  set href(value) {{ this.attributes.href = String(value); }}
  set target(value) {{ this.attributes.target = String(value); }}
  set rel(value) {{ this.attributes.rel = String(value); }}
  get outerHTML() {{
    const attrs = Object.entries(this.attributes).map(([key, value]) => ` ${{key}}="${{encode(value)}}"`).join('');
    return `<${{this.tagName}}${{attrs}}>${{this.innerHTML}}</${{this.tagName}}>`;
  }}
}}

const elements = new Map();
globalThis.document = {{
  createElement: tagName => new Element(tagName),
  getElementById: id => {{
    if (!elements.has(id)) {{ elements.set(id, new Element('div')); }}
    return elements.get(id);
  }},
}};
globalThis.window = {{ location: {{ origin: 'http://localhost' }}, dispatchEvent() {{}} }};
globalThis.CustomEvent = class CustomEvent {{ constructor(type, init) {{ this.type = type; this.detail = init?.detail; }} }};

const {{ renderGenealogyTree }} = await import('{module_path}');
const maliciousName = 'Vie <script>alert(1)</script>';
const maliciousSlug = 'life-<img src=x onerror=alert(1)>';
renderGenealogyTree({{
  nodes: [{{ slug: maliciousSlug, name: maliciousName, status: 'active', active: true, parents: [] }}],
  relationships: [],
  active_relations: [{{
    type: '<img src=x onerror=alert(2)>',
    source: maliciousSlug,
    target: maliciousName,
    status: '<script>alert(3)</script>',
    severity: '<img src=x onerror=alert(4)>',
    updated_at: '<script>alert(5)</script>',
  }}],
  filters: {{ life: maliciousSlug }},
}});

const relationsHtml = elements.get('active-relations-table-body').innerHTML;
const optionsHtml = elements.get('genealogy-relations-life-filter').innerHTML;
if (relationsHtml.includes('<script>') || relationsHtml.includes('<img')) {{
  throw new Error(`relations HTML was not escaped: ${{relationsHtml}}`);
}}
if (optionsHtml.includes('<script>') || optionsHtml.includes('<img')) {{
  throw new Error(`option HTML was not escaped: ${{optionsHtml}}`);
}}
if (!relationsHtml.includes('&lt;script&gt;alert(3)&lt;/script&gt;')) {{
  throw new Error(`escaped relation script fixture missing: ${{relationsHtml}}`);
}}
if (!optionsHtml.includes('Vie &lt;script&gt;alert(1)&lt;/script&gt;')) {{
  throw new Error(`escaped option fixture missing: ${{optionsHtml}}`);
}}
""",
        encoding="utf-8",
    )

    subprocess.run(["node", str(script)], check=True)


def test_cockpit_loader_keeps_available_data_when_cockpit_endpoint_fails(tmp_path: Path) -> None:
    """Exercise the cockpit loader against a failed /api/cockpit response."""
    script = tmp_path / "cockpit_partial_failure_check.mjs"
    module_path = (Path.cwd() / DASHBOARD_STATIC / "render-cockpit.js").as_uri()
    script.write_text(
        f"""
class ClassList {{
  constructor() {{ this.values = new Set(); }}
  add(...names) {{ for (const name of names) {{ this.values.add(name); }} }}
  remove(...names) {{ for (const name of names) {{ this.values.delete(name); }} }}
  toggle(name, force) {{
    const shouldAdd = force === undefined ? !this.values.has(name) : Boolean(force);
    if (shouldAdd) {{ this.values.add(name); }} else {{ this.values.delete(name); }}
    return shouldAdd;
  }}
  contains(name) {{ return this.values.has(name); }}
}}

class Element {{
  constructor(tagName) {{
    this.tagName = tagName;
    this.children = [];
    this.dataset = {{}};
    this.attributes = {{}};
    this.classList = new ClassList();
    this._textContent = '';
    this._innerHTML = null;
    this.value = '';
    this.disabled = false;
    this.eventListeners = {{}};
  }}
  appendChild(child) {{ this.children.push(child); this._innerHTML = null; return child; }}
  insertBefore(child, before) {{
    const index = this.children.indexOf(before);
    if (index < 0) {{ this.children.unshift(child); }} else {{ this.children.splice(index, 0, child); }}
    this._innerHTML = null;
    return child;
  }}
  replaceChildren(...children) {{ this.children = []; this._textContent = ''; this._innerHTML = null; for (const child of children) {{ this.appendChild(child); }} }}
  querySelector() {{ return this.children.find(child => child.className === 'state-layer') ?? null; }}
  addEventListener(type, handler) {{ this.eventListeners[type] = handler; }}
  setAttribute(name, value) {{ this.attributes[name] = String(value); }}
  set textContent(value) {{ this._textContent = String(value ?? ''); this.children = []; this._innerHTML = null; }}
  get textContent() {{ return this._textContent + this.children.map(child => child.textContent ?? '').join(''); }}
  set innerHTML(value) {{ this._innerHTML = String(value ?? ''); this.children = []; this._textContent = ''; }}
  get innerHTML() {{ return this._innerHTML !== null ? this._innerHTML : this.textContent; }}
  set className(value) {{ this.attributes.class = String(value); if (value === 'state-layer') {{ this._className = value; }} }}
  get className() {{ return this._className ?? this.attributes.class ?? ''; }}
  set title(value) {{ this.attributes.title = String(value); }}
  set colSpan(value) {{ this.attributes.colspan = String(value); }}
  get firstChild() {{ return this.children[0] ?? null; }}
  get options() {{ return this.children.filter(child => child.tagName === 'option'); }}
}}

const elements = new Map();
const ids = [
  'stale-data-banner','operator-lives-summary','operator-lives-total','operator-selected-life',
  'operator-alive-lives','operator-risk-lives','operator-last-activity','operator-mood-energy',
  'operator-trend','operator-liveness','digital-life-status','digital-life-health',
  'digital-life-active-objectives','digital-life-last-message','digital-life-select',
  'digital-life-safe-actions','operator-action-life-select','operator-action-help',
  'critical-current-life-target','cockpit-status','kpi-health','kpi-trend','kpi-accepted',
  'kpi-alerts','kpi-liveness-index','kpi-next-action','essential-selected-life',
  'essential-active-incidents','raw-cockpit-json','kpi-actions','daily-skills-table-body',
  'kpi-active-objectives-list','kpi-priority-changes-list','kpi-objective-links-list',
  'kpi-liveness-proofs','sandbox-governance-empty','sandbox-breaker-status',
  'sandbox-recent-violations','sandbox-last-skill','sandbox-cooldown-remaining',
  'sandbox-corrective-action','governance-breaker-threshold','governance-breaker-window',
  'governance-breaker-cooldown','governance-safe-mode','governance-mutation-quota',
  'ctx-governance-diagnostics'
];
for (const id of ids) {{ elements.set(id, new Element(id.endsWith('select') ? 'select' : 'div')); }}

globalThis.document = {{
  createElement: tagName => new Element(tagName),
  getElementById: id => elements.get(id) ?? null,
}};
globalThis.window = {{ location: {{ origin: 'http://localhost' }}, dispatchEvent() {{}} }};
globalThis.CustomEvent = class CustomEvent {{ constructor(type, init) {{ this.type = type; this.detail = init?.detail; }} }};

globalThis.fetch = async url => {{
  const path = String(url);
  if (path.startsWith('/dashboard/context')) {{
    return {{ ok: true, json: async () => ({{registry_lives_count: 2, registry_state: {{active: 'alpha'}}}}) }};
  }}
  if (path.startsWith('/lives/comparison')) {{
    return {{ ok: true, json: async () => ({{
      table: [{{life: 'alpha', selected_life: true, current_health_score: 88.4, last_activity: '2026-05-12T10:00:00Z', life_status: 'active', life_liveness_index: 91.2}}],
      life_metrics_contract: {{counts: {{total_lives: 2, alive_lives: 1, dead_lives: 1}}}},
    }}) }};
  }}
  if (path.startsWith('/api/cockpit/essential')) {{
    return {{ ok: true, json: async () => ({{global_status: 'stable', selected_life: 'alpha', next_action: 'observer'}}) }};
  }}
  if (path.startsWith('/api/cockpit')) {{
    return {{ ok: false, status: 503, json: async () => ({{detail: 'boom'}}) }};
  }}
  throw new Error(`unexpected fetch ${{path}}`);
}};

const {{ loadCockpit }} = await import('{module_path}');
await loadCockpit();

const total = elements.get('operator-lives-total').textContent;
const selected = elements.get('operator-selected-life').textContent;
const health = elements.get('digital-life-health').textContent;
const banner = elements.get('stale-data-banner').textContent;
const raw = elements.get('raw-cockpit-json').textContent;
if (total !== '2') {{ throw new Error(`available context was not rendered: ${{total}}`); }}
if (!selected.includes('alpha')) {{ throw new Error(`available selected life was not rendered: ${{selected}}`); }}
if (health === 'Chargement…' || health !== '88.4') {{ throw new Error(`available life metrics were not rendered: ${{health}}`); }}
if (!banner.includes('Données cockpit partielles') || !banner.includes('cockpit: HTTP 503')) {{ throw new Error(`warning banner missing: ${{banner}}`); }}
if (!raw.includes('"global_status": "warning"')) {{ throw new Error(`fallback cockpit payload missing: ${{raw}}`); }}
""",
        encoding="utf-8",
    )

    subprocess.run(["node", str(script)], check=True)


def test_dashboard_bootstrap_keeps_local_handlers_when_websocket_fails(tmp_path: Path) -> None:
    """A WebSocket construction error must not disable local dashboard controls."""
    script = tmp_path / "dashboard_websocket_failure_check.mjs"
    module_path = (Path.cwd() / DASHBOARD_STATIC / "bootstrap.js").as_uri()
    script.write_text(
        f"""
class ClassList {{
  constructor() {{ this.values = new Set(); }}
  add(...names) {{ names.forEach(name => this.values.add(name)); }}
  remove(...names) {{ names.forEach(name => this.values.delete(name)); }}
  toggle(name, force) {{
    const shouldAdd = force === undefined ? !this.values.has(name) : Boolean(force);
    if (shouldAdd) {{ this.values.add(name); }} else {{ this.values.delete(name); }}
    return shouldAdd;
  }}
  contains(name) {{ return this.values.has(name); }}
}}

class Element {{
  constructor(tagName, id = '') {{
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.children = [];
    this.parentElement = null;
    this.dataset = {{}};
    this.attributes = {{}};
    this.classList = new ClassList();
    this.style = {{}};
    this.value = '';
    this.disabled = false;
    this.onclick = null;
    this.onchange = null;
    this.eventListeners = {{}};
    this.offsetParent = {{}};
    this._textContent = '';
    this._innerHTML = null;
    this._className = '';
    this.open = true;
    this.tabIndex = 0;
  }}
  appendChild(child) {{ child.parentElement = this; this.children.push(child); return child; }}
  prepend(child) {{ child.parentElement = this; this.children.unshift(child); return child; }}
  insertBefore(child, before) {{
    child.parentElement = this;
    const index = this.children.indexOf(before);
    if (index < 0) {{ this.children.unshift(child); }} else {{ this.children.splice(index, 0, child); }}
    return child;
  }}
  replaceChildren(...children) {{ this.children = []; children.forEach(child => this.appendChild(child)); }}
  querySelector(selector) {{ return this.querySelectorAll(selector)[0] ?? null; }}
  querySelectorAll(selector) {{ return queryWithin(this.children, selector); }}
  addEventListener(type, handler) {{ this.eventListeners[type] = handler; }}
  setAttribute(name, value) {{ this.attributes[name] = String(value); }}
  getAttribute(name) {{ return this.attributes[name] ?? null; }}
  matches(selector) {{ return selector === 'details' && this.tagName === 'DETAILS'; }}
  closest(selector) {{
    let node = this;
    while (node) {{
      if (selector === '.tab-pane' && node.classList.contains('tab-pane')) {{ return node; }}
      node = node.parentElement;
    }}
    return null;
  }}
  set textContent(value) {{ this._textContent = String(value ?? ''); this._innerHTML = null; }}
  get textContent() {{ return this._textContent + this.children.map(child => child.textContent ?? '').join(''); }}
  set innerHTML(value) {{ this._innerHTML = String(value ?? ''); this.children = []; }}
  get innerHTML() {{ return this._innerHTML ?? this.textContent; }}
  set className(value) {{
    this._className = String(value ?? '');
    this.classList = new ClassList();
    this._className.split(/\\s+/).filter(Boolean).forEach(name => this.classList.add(name));
  }}
  get className() {{ return this._className; }}
  set title(value) {{ this.attributes.title = String(value); }}
  get firstChild() {{ return this.children[0] ?? null; }}
  get options() {{ return this.children.filter(child => child.tagName === 'OPTION'); }}
}}

const allElements = [];
const elements = new Map();
const register = element => {{ allElements.push(element); if (element.id) {{ elements.set(element.id, element); }} return element; }};
const make = (tagName, id = '', className = '') => {{ const el = register(new Element(tagName, id)); if (className) {{ el.className = className; }} return el; }};
const queryWithin = (roots, selector) => {{
  const visited = [];
  const walk = node => {{ visited.push(node); node.children.forEach(walk); }};
  roots.forEach(walk);
  if (selector === '.tab-trigger') {{ return visited.filter(el => el.classList.contains('tab-trigger')); }}
  if (selector === '.tab-pane') {{ return visited.filter(el => el.classList.contains('tab-pane')); }}
  if (selector === '[data-essential-level]') {{ return visited.filter(el => el.dataset.essentialLevel !== undefined); }}
  if (selector === '.technical-only') {{ return visited.filter(el => el.classList.contains('technical-only')); }}
  if (selector === '.critical-actions-bar [data-dashboard-action]') {{ return visited.filter(el => el.dataset.dashboardAction !== undefined); }}
  if (selector === '[data-expand-target]') {{ return []; }}
  if (selector === ':scope > .state-layer') {{ return []; }}
  return [];
}};

const body = make('body');
const liveStatus = make('span', 'live-status');
liveStatus.textContent = 'Lecture en direct';
const result = make('div', 'critical-action-result');
const essential = make('button', 'toggle-essential');
const technical = make('button', 'toggle-technical-details');
const actionBar = make('div', '', 'critical-actions-bar');
const birth = make('button', 'critical-birth');
birth.dataset.dashboardAction = 'birth';
actionBar.appendChild(birth);
const birthName = make('input', 'operator-birth-name');
birthName.value = '';
const help = make('div', 'operator-action-help');
const target = make('div', 'critical-current-life-target');
const operatorSelect = make('select', 'operator-action-life-select');
const tabButton = make('button', 'tab-btn-technique', 'tab-trigger');
tabButton.dataset.tab = 'technique';
const defaultTabButton = make('button', 'tab-btn-decider', 'tab-trigger');
defaultTabButton.dataset.tab = 'decider-maintenant';
const tabPane = make('section', 'tab-technique', 'tab-pane panel-hidden');
const defaultPane = make('section', 'tab-decider-maintenant', 'tab-pane');
const essentialContent = make('div');
essentialContent.dataset.essentialLevel = '3';
body.appendChild(liveStatus);
body.appendChild(result);
body.appendChild(essential);
body.appendChild(technical);
body.appendChild(actionBar);
body.appendChild(birthName);
body.appendChild(help);
body.appendChild(target);
body.appendChild(operatorSelect);
body.appendChild(defaultTabButton);
body.appendChild(tabButton);
body.appendChild(defaultPane);
body.appendChild(tabPane);
body.appendChild(essentialContent);

const storage = new Map();
globalThis.document = {{
  body,
  visibilityState: 'hidden',
  createElement: tagName => register(new Element(tagName)),
  getElementById: id => elements.get(id) ?? null,
  querySelectorAll: selector => queryWithin([body], selector),
}};
globalThis.window = {{
  location: {{ host: 'localhost', hash: '' }},
  __singularSelectedLifeActionBinding: 'false',
  addEventListener() {{}},
  dispatchEvent() {{}},
  confirm: () => true,
}};
globalThis.location = globalThis.window.location;
globalThis.localStorage = {{
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
}};
globalThis.CustomEvent = class CustomEvent {{ constructor(type, init) {{ this.type = type; this.detail = init?.detail; }} }};
globalThis.MutationObserver = class MutationObserver {{ observe() {{}} }};
globalThis.fetch = async () => {{ throw new Error('fetch should not run while document is hidden'); }};
globalThis.setInterval = () => 0;
globalThis.clearInterval = () => {{}};
globalThis.WebSocket = class WebSocket {{ constructor() {{ throw new Error('socket denied'); }} }};

const {{ bootstrapDashboard }} = await import('{module_path}');
bootstrapDashboard();

if (liveStatus.textContent !== 'temps réel indisponible') {{ throw new Error(`unexpected live status: ${{liveStatus.textContent}}`); }}
if (typeof essential.onclick !== 'function') {{ throw new Error('toggle-essential has no handler'); }}
essential.onclick();
if (!body.classList.contains('essential-mode')) {{ throw new Error('toggle-essential handler did not toggle essential mode'); }}
if (typeof tabButton.onclick !== 'function') {{ throw new Error('tab trigger has no handler'); }}
tabButton.onclick();
if (tabPane.classList.contains('panel-hidden')) {{ throw new Error('tab trigger handler did not activate the pane'); }}
if (typeof birth.onclick !== 'function') {{ throw new Error('dashboard action has no handler'); }}
birth.onclick();
if (!result.textContent.includes('Saisissez le nom exact')) {{ throw new Error(`dashboard action handler did not validate locally: ${{result.textContent}}`); }}
""",
        encoding="utf-8",
    )

    subprocess.run(["node", str(script)], check=True)


def test_empty_lives_comparison_keeps_birth_action_enabled(tmp_path: Path) -> None:
    """Critical birth action remains usable when /lives/comparison has no lives."""
    script = tmp_path / "empty_lives_birth_action_check.mjs"
    module_path = (Path.cwd() / DASHBOARD_STATIC / "actions.js").as_uri()
    script.write_text(
        f"""
class ClassList {{
  constructor() {{ this.values = new Set(); }}
  add(...names) {{ names.forEach(name => this.values.add(name)); }}
  remove(...names) {{ names.forEach(name => this.values.delete(name)); }}
  toggle(name, force) {{
    const shouldAdd = force === undefined ? !this.values.has(name) : Boolean(force);
    if (shouldAdd) {{ this.values.add(name); }} else {{ this.values.delete(name); }}
    return shouldAdd;
  }}
  contains(name) {{ return this.values.has(name); }}
}}

class Element {{
  constructor(tagName, id = '') {{
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.children = [];
    this.dataset = {{}};
    this.attributes = {{}};
    this.classList = new ClassList();
    this.value = '';
    this.disabled = false;
    this._textContent = '';
    this._innerHTML = null;
  }}
  appendChild(child) {{ this.children.push(child); return child; }}
  addEventListener() {{}}
  setAttribute(name, value) {{ this.attributes[name] = String(value); }}
  getAttribute(name) {{ return this.attributes[name] ?? null; }}
  set textContent(value) {{ this._textContent = String(value ?? ''); this.children = []; this._innerHTML = null; }}
  get textContent() {{ return this._textContent + this.children.map(child => child.textContent ?? '').join(''); }}
  set innerHTML(value) {{ this._innerHTML = String(value ?? ''); this.children = []; this._textContent = ''; }}
  get innerHTML() {{ return this._innerHTML ?? this.textContent; }}
  set title(value) {{ this.attributes.title = String(value); }}
  get title() {{ return this.attributes.title ?? ''; }}
  get options() {{ return this.children.filter(child => child.tagName === 'OPTION'); }}
}}

const elements = new Map();
const register = (tagName, id) => {{ const el = new Element(tagName, id); elements.set(id, el); return el; }};
register('select', 'operator-action-life-select').dataset.registryState = 'loading';
register('p', 'operator-action-help');
register('span', 'critical-current-life-target');
register('input', 'operator-birth-name').value = 'Nouvelle Vie';
const birth = register('button', 'critical-birth');
const archive = register('button', 'critical-archive');
const talk = register('button', 'critical-talk');
const emergency = register('button', 'critical-emergency-stop');
register('div', 'critical-action-result');

globalThis.document = {{
  createElement: tagName => new Element(tagName),
  getElementById: id => elements.get(id) ?? null,
}};
globalThis.window = {{ dispatchEvent() {{}} }};
globalThis.CustomEvent = class CustomEvent {{ constructor(type, init) {{ this.type = type; this.detail = init?.detail; }} }};

const {{ updateOperatorLifeOptions }} = await import('{module_path}');
const emptyComparison = {{ table: [] }};
updateOperatorLifeOptions(emptyComparison.table);

const help = elements.get('operator-action-help').textContent;
if (help !== 'Aucune vie détectée dans le registre') {{ throw new Error(`unexpected help message: ${{help}}`); }}
if (birth.disabled) {{ throw new Error('Créer une vie was disabled for an empty /lives/comparison table'); }}
if (birth.getAttribute('aria-disabled') !== 'false') {{ throw new Error('Créer une vie was not exposed as active'); }}
if (birth.classList.contains('is-disabled')) {{ throw new Error('Créer une vie looked disabled'); }}
for (const [label, button] of [['archive', archive], ['talk', talk], ['emergency_stop', emergency]]) {{
  if (!button.disabled) {{ throw new Error(`${{label}} should be disabled without a valid life`); }}
  if (button.getAttribute('aria-disabled') !== 'true') {{ throw new Error(`${{label}} aria-disabled missing`); }}
}}
""",
        encoding="utf-8",
    )

    subprocess.run(["node", str(script)], check=True)
