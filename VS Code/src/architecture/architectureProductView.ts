export const productFormHtml = `
  <div id="product-ui">
    <header class="product-header">
      <div><span class="eyebrow">Spring Boot / Layered Architecture</span><h1>Architecture Governance</h1>
        <p>Project-specific architecture governance for Spring Boot</p></div>
      <button id="product-view-violations" type="button">View Violations <span id="product-count" class="count-badge">Not checked</span></button>
    </header>
    <main class="product-main">
      <div id="product-configuration">
        <section class="product-project" aria-label="Project status">
          <dl class="project-status-grid">
            <div><dt>Project</dt><dd id="product-project-name">No project analyzed</dd></div>
            <div><dt>Analysis</dt><dd id="product-analysis" class="status-badge">Not analyzed</dd></div>
            <div><dt>AI Context</dt><dd id="product-sync" class="status-badge">Not synchronized</dd></div>
            <div><dt>Approved Rules</dt><dd id="product-approved-count" class="status-badge badge-info">0</dd></div>
          </dl>
          <div class="action-row"><button id="product-scan" type="button">Analyze Project</button>
            <button id="product-sync-action" class="secondary" type="button" disabled>Sync AI Context</button></div>
          <p id="product-project-notice" class="helper" role="status">Analyze your Spring Boot project to get started.</p>
        </section>
        <section class="product-section" aria-labelledby="product-approved-heading">
          <div class="product-section-heading"><h2 id="product-approved-heading">Approved Architecture Rules</h2><span class="policy-label">Base policy active</span></div>
          <p class="helper">Base policy: Spring Boot Layered Architecture</p>
          <div id="product-approved-list"><p class="product-empty">No project-specific architecture rules have been added here yet.</p></div>
          <p class="helper catalog-note">Shows confirmed approvals from this workspace, project and backend.</p>
        </section>
        <section class="product-section assistant-section" aria-labelledby="product-assistant-heading">
          <h2 id="product-assistant-heading">Architecture Assistant</h2>
          <p class="helper">Describe a project-specific architecture requirement in natural language.</p>
          <div id="product-conversation" class="conversation" role="log" aria-live="polite" aria-label="Architecture assistant conversation">
            <p class="product-empty">Add a requirement to start defining your project policy.</p>
          </div>
          <form id="product-rule-form" class="composer">
            <label for="product-requirement">Architecture requirement</label>
            <textarea id="product-requirement" rows="3" placeholder="Describe a project-specific architecture rule..."></textarea>
            <div class="composer-footer"><span class="helper">Ctrl+Enter or ⌘+Enter to send. Enter adds a new line.</span>
              <button id="product-generate" type="submit">Generate Rule</button></div>
          </form>
          <p id="product-rule-notice" class="helper" role="status">Review each interpretation before approving it.</p>
        </section>
      </div>
      <div id="product-violations" hidden>
        <div class="action-row"><button id="product-back" class="secondary" type="button">← Back to Configuration</button></div>
        <section class="product-section" aria-labelledby="product-violations-heading">
          <div class="product-section-heading"><h2 id="product-violations-heading">Architecture Violations</h2>
            <button id="product-check" type="button" disabled>Check Conformance</button></div>
          <p id="product-conformance-state" role="status" aria-live="polite">Architecture conformance has not been checked.</p>
          <div class="violation-totals" aria-label="Violation summary">
            <div class="summary-card summary-total"><span id="product-total">—</span><h3>Total Violations</h3></div>
            <div class="summary-card summary-dependency"><span id="product-dependency">—</span><h3>Dependency Violations</h3></div>
            <div class="summary-card summary-structure"><span id="product-structure">—</span><h3>Structure Violations</h3></div>
          </div>
          <div id="product-findings"><p class="product-empty">Check conformance to review architecture findings.</p></div>
        </section>
      </div>
    </main>
  </div>`;

export const productStyles = `
  #product-ui {
    --product-surface: color-mix(in srgb, var(--vscode-sideBar-background, var(--vscode-editor-background)) 94%, var(--vscode-foreground) 6%);
    --product-raised: color-mix(in srgb, var(--vscode-editorWidget-background, var(--vscode-editor-background)) 92%, var(--vscode-foreground) 8%);
    --product-border: color-mix(in srgb, var(--vscode-widget-border, var(--vscode-panel-border)) 80%, var(--vscode-foreground) 20%);
    --product-success: var(--vscode-testing-iconPassed, var(--vscode-charts-green, var(--vscode-focusBorder)));
    --product-warning: var(--vscode-editorWarning-foreground, var(--vscode-focusBorder));
    --product-error: var(--vscode-errorForeground);
    --product-info: var(--vscode-editorInfo-foreground, var(--vscode-focusBorder));
    max-width: 1040px; margin: auto;
  }
  /* Keep every button state explicit so browser pressed/focus colors cannot take over. */
  #product-ui button, #product-ui button:focus {
    appearance: none; background: var(--vscode-button-background); color: var(--vscode-button-foreground);
    border: 1px solid var(--vscode-button-border, transparent); border-radius: 5px; box-shadow: none;
    min-height: 34px; padding: 7px 13px; font-weight: 500;
    transition: background-color 120ms ease, border-color 120ms ease;
  }
  #product-ui button:hover:enabled, #product-ui button:active:enabled {
    background: var(--vscode-button-hoverBackground, var(--vscode-button-background)); color: var(--vscode-button-foreground);
  }
  #product-ui button.secondary, #product-ui button.secondary:focus {
    background: var(--vscode-button-secondaryBackground, var(--product-raised));
    color: var(--vscode-button-secondaryForeground, var(--vscode-foreground)); border-color: var(--product-border);
  }
  #product-ui button.secondary:hover:enabled, #product-ui button.secondary:active:enabled {
    background: var(--vscode-button-secondaryHoverBackground, var(--vscode-list-hoverBackground, var(--product-raised)));
    color: var(--vscode-button-secondaryForeground, var(--vscode-foreground)); border-color: var(--vscode-focusBorder);
  }
  #product-ui button:focus-visible { outline: 2px solid var(--vscode-focusBorder); outline-offset: 2px; }
  #product-ui button:disabled { opacity: .6; cursor: default; }
  .product-header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; margin: 8px 0 24px; }
  .product-header h1 { font-size: 22px; font-weight: 600; margin: 4px 0 6px; letter-spacing: -.3px; }
  .product-header p { color: var(--vscode-descriptionForeground); font-size: 12px; margin: 0; }
  .eyebrow { color: var(--vscode-descriptionForeground); text-transform: uppercase; font-size: 10px; letter-spacing: .9px; }
  .product-main { max-width: none; }
  .product-project { background: var(--product-surface); border: 1px solid var(--product-border); border-radius: 8px; padding: 16px 18px; }
  .project-status-grid { display: grid; grid-template-columns: minmax(0, 2fr) repeat(3, minmax(0, 1fr)); gap: 16px; margin: 0; }
  .project-status-grid dd { font-size: 12px; margin: 5px 0 0; }
  .product-project .action-row { margin-bottom: 8px; }
  .product-project .helper { margin-bottom: 0; }
  .product-section { margin: 28px 0; min-width: 0; }
  .product-section h2 { font-size: 15px; font-weight: 600; margin: 0 0 8px; }
  .product-section-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px; }
  .product-section-heading h2 { margin: 0; }
  .policy-label, .count-badge, .rule-label, .status-badge {
    display: inline-block; width: fit-content; max-width: 100%; border-radius: 5px; padding: 3px 8px; font-size: 11px; line-height: 1.4;
    background: var(--product-raised); color: var(--vscode-foreground); border: 1px solid var(--product-border); overflow-wrap: anywhere;
  }
  .project-status-grid .status-badge { font-size: 11px; }
  .count-badge { margin-left: 8px; font-weight: 600; }
  .policy-label { color: var(--vscode-descriptionForeground); background: var(--product-surface); }
  .badge-success { --badge-accent: var(--product-success); }
  .badge-warning { --badge-accent: var(--product-warning); }
  .badge-error { --badge-accent: var(--product-error); }
  .badge-info { --badge-accent: var(--product-info); }
  .badge-success, .badge-warning, .badge-error, .badge-info {
    color: var(--vscode-foreground); background: color-mix(in srgb, var(--badge-accent) 12%, var(--product-raised));
    border-color: color-mix(in srgb, var(--badge-accent) 55%, var(--product-border));
  }
  .product-empty { padding: 18px; margin: 12px 0; color: var(--vscode-descriptionForeground); background: var(--product-surface);
    border: 1px dashed var(--product-border); border-radius: 8px; font-size: 12px; overflow-wrap: anywhere; }
  .catalog-note { margin-top: 10px; font-size: 10px; }
  .approved-rule { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 10px; padding: 12px; margin: 10px 0;
    background: var(--product-surface); border: 1px solid var(--product-border); border-radius: 8px; }
  .approved-rule p { margin: 0; overflow-wrap: anywhere; }
  .approved-rule .rule-copy { flex: 1; min-width: 0; }
  .approved-rule small { display: block; color: var(--vscode-descriptionForeground); margin-top: 4px; overflow-wrap: anywhere; }
  .assistant-section { background: var(--product-surface); border: 1px solid var(--product-border); border-radius: 8px; padding: 18px; }
  .conversation { display: flex; flex-direction: column; gap: 12px; max-height: 620px; overflow-y: auto; padding: 2px; overflow-wrap: anywhere; }
  .chat-message { padding: 14px; border: 1px solid var(--product-border); border-radius: 8px; max-width: 95%; min-width: 0; }
  .chat-message h3 { margin: 0 0 8px; font-size: 11px; font-weight: 600; color: var(--vscode-foreground); }
  .chat-message p { margin: 6px 0; white-space: pre-wrap; }
  .chat-user { align-self: flex-end; background: color-mix(in srgb, var(--product-info) 9%, var(--product-raised));
    border-color: color-mix(in srgb, var(--product-info) 35%, var(--product-border)); }
  .chat-assistant { align-self: stretch; background: var(--product-raised); }
  .chat-warning { border-left: 3px solid var(--product-warning); background: color-mix(in srgb, var(--product-warning) 4%, var(--product-raised)); }
  .chat-error { border-left: 3px solid var(--product-error); }
  .chat-success { border-left: 3px solid var(--product-success); }
  .chat-message dl { display: grid; grid-template-columns: 95px minmax(0, 1fr); gap: 4px 12px; margin: 12px 0; font-size: 12px; }
  .chat-message dd { margin: 0; }
  .chat-message .action-row { margin-bottom: 0; }
  .chat-loading { color: var(--vscode-descriptionForeground); }
  .composer { margin-top: 16px; border: 1px solid var(--vscode-input-border, var(--product-border)); border-radius: 8px; padding: 12px; background: var(--vscode-input-background); }
  .composer:focus-within { border-color: var(--vscode-focusBorder); }
  .composer label { margin: 0; font-size: 11px; color: var(--vscode-descriptionForeground); }
  .composer textarea { min-height: 80px; border: 0; border-radius: 0; padding: 8px 0; margin: 0; }
  .composer-footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
  .composer-footer .helper { font-size: 10px; margin: 0; }
  .violation-totals { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 18px 0 24px; }
  .summary-card { padding: 14px; border: 1px solid var(--product-border); border-radius: 8px; background: var(--product-surface); }
  .summary-total { --count-accent: var(--product-error); }
  .summary-dependency { --count-accent: var(--product-warning); }
  .summary-structure { --count-accent: var(--product-info); }
  .summary-card:has(.count-positive) { border-top: 3px solid var(--count-accent); background: color-mix(in srgb, var(--count-accent) 5%, var(--product-surface)); }
  .summary-card:has(.count-zero) { border-top: 3px solid var(--product-success); }
  .violation-totals span { display: block; font-size: 27px; font-weight: 600; }
  .violation-totals .count-positive { color: var(--count-accent); }
  .violation-totals .count-zero { color: var(--product-success); }
  .violation-totals h3 { margin: 5px 0 0; font-size: 11px; font-weight: 400; color: var(--vscode-descriptionForeground); }
  .product-finding { padding: 16px; margin: 14px 0; background: var(--product-surface); border: 1px solid var(--product-border); border-radius: 8px; overflow-wrap: anywhere; }
  .product-finding h4 { font-size: 13px; margin: 10px 0 12px; }
  .finding-badges { display: flex; flex-wrap: wrap; gap: 6px; }
  .product-finding dl { display: grid; grid-template-columns: 85px minmax(0, 1fr); gap: 4px 12px; font-size: 12px; }
  .product-finding dd { margin: 0; }
  .product-current-file { border-left: 2px solid var(--vscode-focusBorder); padding-left: 12px; }
  .product-current-file .product-finding { background: var(--product-raised); border-color: color-mix(in srgb, var(--vscode-focusBorder) 45%, var(--product-border)); }
  .product-current-file > h3, .product-other-files > h3 { margin-top: 20px; overflow-wrap: anywhere; }
  .product-finding:hover { border-color: var(--vscode-focusBorder); }
  @media (prefers-reduced-motion: reduce) { #product-ui button { transition: none; } }
  @media (max-width: 600px) { .project-status-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  @media (max-width: 440px) {
    .product-header h1 { font-size: 20px; }
    .product-project { padding: 14px; }
    .assistant-section { padding: 12px; }
    .chat-message { max-width: 100%; }
    .chat-message dl, .product-finding dl { grid-template-columns: minmax(0, 1fr); gap: 2px; }
    .chat-message dd, .product-finding dd { margin-bottom: 6px; }
    .violation-totals { gap: 6px; }
    .violation-totals > div { padding: 10px; }
    .violation-totals span { font-size: 20px; }
  }
`;

export const productWebviewScript = `
(() => {
  const byId = id => document.getElementById('product-' + id);
  const post = message => productApi.postMessage(message);
  const productApi = vscode;
  const conversation = byId('conversation');
  let busy = false, analysisBusy = false, syncing = false, checking = false;
  let canSync = false, canCheck = false, canApprove = false, awaitingConflict = false;
  let actions = [], conflictActions = [], loading, turn = false;
  function node(tag, text, className) {
    const item = document.createElement(tag);
    if (text !== undefined) { item.textContent = text; }
    if (className) { item.className = className; }
    return item;
  }
  function updateButtons() {
    const working = busy || analysisBusy || syncing || checking;
    byId('requirement').disabled = working;
    byId('generate').disabled = working;
    byId('scan').disabled = working;
    byId('sync-action').disabled = working || !canSync;
    byId('check').disabled = working || !canCheck;
    for (const button of actions) { button.disabled = working || !canApprove; }
    for (const button of conflictActions) { button.disabled = !awaitingConflict; }
  }
  function retireActions() {
    for (const button of [...actions, ...conflictActions]) { button.disabled = true; }
    actions = []; conflictActions = [];
  }
  function message(author, text, tone = '') {
    if (!turn) { conversation.replaceChildren(); turn = true; }
    const card = node('article', undefined, 'chat-message chat-' + (author === 'You' ? 'user' : 'assistant') + (tone ? ' chat-' + tone : ''));
    card.append(node('h3', author), node('p', text));
    conversation.append(card);
    conversation.scrollTop = conversation.scrollHeight;
    return card;
  }
  function detail(parent, label, value) {
    parent.append(node('dt', label), node('dd', value === undefined || value === null ? 'Not supplied' : String(value)));
  }
  function button(parent, text, callback, secondary = false) {
    const item = node('button', text, secondary ? 'secondary' : '');
    item.type = 'button'; item.addEventListener('click', callback); parent.append(item); return item;
  }
  function stopLoading() { if (loading) { loading.hidden = true; loading = undefined; } }
  function generate(event) {
    event.preventDefault();
    if (busy || analysisBusy || syncing || checking) { return; }
    const requirement = byId('requirement').value.trim();
    if (!requirement) { byId('rule-notice').textContent = 'Describe an architecture requirement first.'; return; }
    retireActions(); canApprove = false; awaitingConflict = false;
    busy = true; updateButtons();
    byId('rule-notice').textContent = 'Interpreting architecture requirement...';
    post({ type: 'generate', requirement });
  }
  byId('rule-form').addEventListener('submit', generate);
  byId('requirement').addEventListener('keydown', event => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.isComposing) { generate(event); }
  });
  byId('requirement').addEventListener('input', () => {
    if (busy) { return; }
    canApprove = false; retireActions(); updateButtons(); post({ type: 'edit' });
  });
  byId('scan').addEventListener('click', () => { if (!byId('scan').disabled) { analysisBusy = true; updateButtons(); post({ type: 'scan' }); } });
  byId('sync-action').addEventListener('click', () => { if (!byId('sync-action').disabled) { syncing = true; updateButtons(); post({ type: 'sync' }); } });
  byId('check').addEventListener('click', () => { if (!byId('check').disabled) { checking = true; updateButtons(); post({ type: 'checkConformance' }); } });
  function navigate(violations) {
    byId('configuration').hidden = violations;
    byId('violations').hidden = !violations;
    byId('view-violations').hidden = violations;
    (violations ? byId('back') : byId('view-violations')).focus();
  }
  byId('view-violations').addEventListener('click', () => navigate(true));
  byId('back').addEventListener('click', () => navigate(false));
  function renderApproved(rules) {
    byId('approved-count').textContent = String(rules.length);
    const list = byId('approved-list'); list.replaceChildren();
    if (!rules.length) { list.append(node('p', 'No project-specific architecture rules have been added here yet.', 'product-empty')); }
    for (const envelope of rules) {
      const rule = envelope.rule;
      const card = node('article', undefined, 'approved-rule');
      const copy = node('div', undefined, 'rule-copy');
      copy.append(node('p', rule.source.name + ' → ' + rule.relationship + ' → ' + rule.target.name),
        node('small', envelope.rule_id + ' · ' + rule.rule_type + (rule.is_exception ? ' · Exception' : '')));
      card.append(node('span', rule.action, 'rule-label badge-success'), copy); list.append(card);
    }
  }
  function reviewActions(card) {
    if (!canApprove) { return; }
    const row = node('div', undefined, 'action-row');
    actions.push(button(row, 'Approve Rule', () => {
      if (busy || !canApprove) { return; } busy = true;
      byId('rule-notice').textContent = 'Checking conflicts and approving rule...';
      updateButtons(); post({ type: 'approve' });
    }));
    actions.push(button(row, 'Cancel', () => {
      if (busy) { return; } canApprove = false; retireActions();
      message('Architecture Assistant', 'Interpretation cancelled. No rule was saved.'); post({ type: 'edit' }); updateButtons();
    }, true));
    card.append(row);
  }
  function renderFindings(items, parent, result, state) {
    for (const item of items) {
      const card = node('article', undefined, 'product-finding');
      const badges = node('div', undefined, 'finding-badges');
      const metadata = result.rule_metadata[item.rule_id];
      badges.append(node('span', item.severity === 'ERROR' ? 'Error' : item.severity === 'WARNING' ? 'Warning' : 'Info',
        'rule-label badge-' + (item.severity === 'ERROR' ? 'error' : item.severity === 'WARNING' ? 'warning' : 'info')),
        node('span', metadata.rule_source === 'BASE' ? 'Base Rule' : 'Custom Rule', 'policy-label' + (metadata.rule_source === 'CUSTOM' ? ' badge-info' : '')));
      card.append(badges, node('h4', item.message));
      const details = node('dl');
      const simple = name => name.split('.').pop();
      detail(details, 'Source', simple(item.source));
      if (item.relationship) { detail(details, 'Relationship', item.relationship); }
      if (item.target) { detail(details, 'Target', simple(item.target)); }
      detail(details, 'Rule', item.rule_id);
      if (item.file_path) { detail(details, 'Location', item.file_path + (item.start_line ? ':' + item.start_line : '')); }
      card.append(details);
      const open = button(card, 'Open Source', () => { if (!open.disabled) { post({ type: 'openViolation', violationId: item.violation_id }); } }, true);
      open.disabled = !state.navigableViolationIds.includes(item.violation_id);
      if (open.disabled) { card.append(node('p', 'Source location unavailable.', 'helper')); }
      parent.append(card);
    }
  }
  function renderConformance(data) {
    const state = data.state, list = byId('findings');
    canCheck = data.canCheck; checking = data.checking;
    list.replaceChildren();
    for (const id of ['total', 'dependency', 'structure']) { byId(id).textContent = '—'; byId(id).className = ''; }
    const checked = state.status === 'checked';
    byId('count').textContent = checked ? String(state.result.summary.total) : state.status === 'stale' ? 'Stale' : state.status === 'checking' ? 'Checking' : 'Not checked';
    byId('count').className = 'count-badge' + (checked ? state.result.summary.total > 0 ? ' badge-error' : ' badge-success'
      : state.status === 'stale' ? ' badge-warning' : state.status === 'checking' ? ' badge-info' : state.status === 'failed' ? ' badge-error' : '');
    byId('conformance-state').textContent = checked ? state.result.conformant ? 'Conformant — no architecture violations detected.' : 'Violations found. Review the findings below.'
      : state.status === 'checking' ? 'Checking architecture conformance...'
      : state.status === 'stale' ? 'Results are stale. Check conformance again before reviewing findings.'
      : state.status === 'failed' ? 'Conformance check failed. ' + state.message
      : state.status === 'cancelled' ? 'Conformance check cancelled.' : 'Architecture conformance has not been checked.';
    if (!checked) {
      list.append(node('p', state.status === 'checking' ? 'Checking your project policy...' : 'Analyze and synchronize your project, then check conformance.', 'product-empty')); return;
    }
    const result = state.result;
    for (const id of ['total', 'dependency', 'structure']) {
      byId(id).textContent = String(data.displaySummary[id]);
      byId(id).className = data.displaySummary[id] > 0 ? 'count-positive' : 'count-zero';
    }
    if (result.conformant) { list.append(node('p', 'No architecture violations detected.', 'product-empty')); }
    function group(title, items, className) {
      const section = node('section', undefined, className); section.append(node('h3', title));
      if (!items.length) { section.append(node('p', 'No architecture violations in this file.', 'product-empty')); }
      renderFindings(items, section, result, state); list.append(section);
    }
    if (data.activeFile && data.violationGroups) {
      group('Current File Violations — ' + data.activeFile.fileName + ' (' + data.violationGroups.currentFileViolations.length + ')', data.violationGroups.currentFileViolations, 'product-current-file');
      if (data.violationGroups.otherViolations.length) { group('Other Project Violations (' + data.violationGroups.otherViolations.length + ')', data.violationGroups.otherViolations, 'product-other-files'); }
    } else if (result.violations.length) { group('Project Violations', result.violations, 'product-other-files'); }
  }
  const reasons = {
    MISSING_SOURCE: 'Specify the source layer, package or component.', MISSING_TARGET: 'Specify the target layer, package or component.',
    UNCLEAR_RELATIONSHIP: 'Clarify the relationship the rule should control.', UNCLEAR_SCOPE: 'Clarify which project scope the requirement applies to.',
    INSUFFICIENT_RULE_INFORMATION: 'Add more information about the architectural constraint.', MULTIPLE_INTERPRETATIONS: 'This requirement has multiple interpretations. Please make it more specific.',
    NOT_ARCHITECTURAL_CONSTRAINT: 'This requirement does not describe an architecture constraint.', UNSUPPORTED_RELATIONSHIP: 'The requested relationship is not supported.'
  };
  window.addEventListener('message', event => {
    const data = event.data;
    if (data.type === 'uiMode') {
      document.getElementById('product-ui').hidden = data.mode !== 'product';
      document.getElementById('developer-ui').hidden = data.mode !== 'developer';
    }
    if (data.type === 'approvedRules') { renderApproved(data.rules); }
    if (data.type === 'analysis') {
      const state = data.state; analysisBusy = ['running', 'selecting'].includes(state.status);
      byId('analysis').textContent = state.status === 'succeeded' ? 'Complete' : analysisBusy ? 'Analyzing...' : state.status === 'failed' ? 'Failed' : 'Not analyzed';
      byId('analysis').className = 'status-badge' + (state.status === 'succeeded' ? ' badge-success' : state.status === 'failed' ? ' badge-error' : analysisBusy ? ' badge-info' : '');
      if (state.status === 'succeeded') { byId('project-name').textContent = state.summary.projectName; }
      byId('project-notice').textContent = state.status === 'succeeded' ? 'Project analyzed. Synchronize the AI context before defining rules.' : state.status === 'failed' ? state.message : analysisBusy ? 'Analyzing project architecture...' : 'Analyze your Spring Boot project to get started.';
      byId('scan').className = state.status === 'succeeded' ? 'secondary' : '';
    }
    if (data.type === 'contextSync') {
      canSync = data.canSync; syncing = data.syncing;
      byId('sync').textContent = data.state.status === 'synchronized' ? 'Synchronized' : syncing ? 'Synchronizing...' : 'Not synchronized';
      byId('sync').className = 'status-badge' + (data.state.status === 'synchronized' ? ' badge-success' : syncing ? ' badge-info' : '');
      byId('sync-action').className = canSync && data.state.status !== 'synchronized' ? '' : 'secondary';
      if (data.state.status === 'synchronized') { byId('project-notice').textContent = 'Ready to define rules and check your project policy.'; }
      else if (data.state.message) { byId('project-notice').textContent = data.state.message; }
    }
    if (data.type === 'conformance') { renderConformance(data); }
    if (data.type === 'busy') { busy = data.busy; if (!busy) { stopLoading(); } }
    if (data.type === 'generationStarted') {
      byId('requirement').value = data.requirement;
      retireActions(); canApprove = false; awaitingConflict = false;
      message('You', data.requirement);
      stopLoading(); loading = message('Architecture Assistant', 'Interpreting architecture requirement...', 'loading');
    }
    if (data.type === 'proposalCleared') { canApprove = false; awaitingConflict = false; retireActions(); }
    if (data.type === 'contextChanged') {
      canApprove = false; awaitingConflict = false; retireActions();
      byId('rule-notice').textContent = 'Project context updated. Generate a new interpretation.';
    }
    if (data.type === 'proposal') {
      stopLoading(); retireActions(); canApprove = data.canApprove;
      const response = data.response, envelope = response.rule;
      const valid = response.json_valid && response.schema_valid;
      const status = envelope && envelope.status;
      const text = !valid ? 'This interpretation could not be validated. Try rephrasing your requirement.'
        : status === 'VALID' ? 'I interpreted your requirement as:'
        : status === 'AMBIGUOUS' ? 'This requirement needs clarification.' : 'This requirement cannot be converted into a supported architecture rule.';
      const card = message('Architecture Assistant', text, canApprove ? '' : 'warning');
      card.append(node('span', valid ? status : 'Validation failed', 'rule-label badge-'
        + (valid && status === 'VALID' ? 'success' : valid && status === 'AMBIGUOUS' ? 'warning' : 'error')));
      if (valid && status === 'VALID') {
        const rule = envelope.rule, details = node('dl');
        detail(details, 'Action', rule.action); detail(details, 'Source', rule.source.name); detail(details, 'Relationship', rule.relationship);
        detail(details, 'Target', rule.target.name); detail(details, 'Scope', rule.scope.type === 'PROJECT' ? 'Project' : rule.scope.type);
        detail(details, 'Rule type', rule.rule_type);
        if (rule.is_exception) { detail(details, 'Exception', 'Yes'); }
        card.append(details);
      } else if (valid && envelope.reason_code) { card.append(node('p', reasons[envelope.reason_code] || envelope.reason_code)); }
      reviewActions(card);
      byId('rule-notice').textContent = canApprove ? 'Review the interpretation before approving it.' : 'Revise your requirement to generate another interpretation.';
    }
    if (data.type === 'conflicts') {
      retireActions(); awaitingConflict = !!data.confirmationRequired;
      byId('rule-notice').textContent = 'Review the conflict before deciding whether to approve.';
      const card = message('Architecture Assistant', 'This rule conflicts with an existing architecture rule.', 'warning');
      for (const conflict of data.conflicts.conflicts) { const details = node('dl'); detail(details, 'Existing rule', conflict.existing_rule_id); detail(details, 'Reason', conflict.reason); card.append(details); }
      const row = node('div', undefined, 'action-row');
      for (const [label, confirmed] of [['Approve Anyway', true], ['Cancel', false]]) {
        conflictActions.push(button(row, label, () => {
          if (!awaitingConflict) { return; } awaitingConflict = false; updateButtons(); post({ type: 'confirmConflict', confirmed });
        }, !confirmed));
      }
      card.append(row);
    }
    if (data.type === 'cancelled') {
      awaitingConflict = false; canApprove = data.canApprove; retireActions();
      reviewActions(message('Architecture Assistant', 'Approval cancelled. The rule has not been approved.'));
    }
    if (data.type === 'approved') {
      stopLoading(); canApprove = false; awaitingConflict = false; retireActions();
      message('Architecture Assistant', data.approval.duplicate ? 'This rule is already approved (' + data.approval.rule_id + '). No duplicate was added.' : 'Rule approved and added to the project architecture policy.', 'success');
      byId('rule-notice').textContent = 'Policy updated. Check conformance to review the project.';
    }
    if (data.type === 'error') {
      stopLoading(); canApprove = data.canApprove; awaitingConflict = false; retireActions();
      reviewActions(message('Architecture Assistant', data.message, 'error'));
      byId('rule-notice').textContent = 'The request could not be completed. You can try again.';
    }
    updateButtons();
    // Scroll after adding fields and actions so the newest decision buttons stay visible.
    if (['generationStarted', 'proposal', 'conflicts', 'cancelled', 'approved', 'error'].includes(data.type)) {
      conversation.scrollTop = conversation.scrollHeight;
    }
  });
  updateButtons();
})();
`;
