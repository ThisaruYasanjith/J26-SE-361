export const analysisFormHtml = `
  <section class="issue-card project-card" aria-labelledby="analysis-heading">
    <div class="section-heading"><span class="step-label">01 / Project</span><h2 id="analysis-heading">Project Architecture</h2></div>
    <p class="helper">Analyze a Spring Boot project, then sync its architecture context.</p>
    <div class="action-row"><button id="scan" type="button">Analyze Project</button>
      <button id="sync" class="secondary" type="button" disabled>Sync AI Context</button></div>
    <div class="status-row" aria-label="Project status" aria-live="polite">
      <span id="analysis-badge" class="status-pill">Analysis: Not analyzed</span>
      <span id="sync-badge" class="status-pill">AI Context: Not synchronized</span>
      <span id="conformance-badge" class="status-pill">Conformance: Not checked</span>
    </div>
    <p id="scan-status" role="status" aria-live="polite">Scan the opened Java project to generate its local architecture context.</p>
    <dl id="scan-summary" class="project-metrics"></dl>
    <p id="sync-status" role="status" aria-live="polite">AI context: not synchronized.</p>
  </section>`;

export const conformanceFormHtml = `
  <section class="issue-card" aria-labelledby="conformance-heading">
    <div class="section-heading"><span class="step-label">03 / Review</span><h2 id="conformance-heading">Architecture Conformance</h2></div>
    <p class="helper">Check the synchronized architecture against your approved rules.</p>
    <div class="action-row"><button id="check-conformance" type="button" disabled>Check Conformance</button>
      <button id="clear-conformance" class="secondary" type="button">Clear results</button></div>
    <p id="conformance-status" role="status" aria-live="polite">Architecture conformance: not checked.</p>
    <dl id="conformance-summary" class="summary-metrics"></dl>
    <div id="violation-list"></div>
    <p class="helper footnote">Architecture violations are determined by the deterministic conformance engine, not by the LLM.</p>
  </section>`;

export const ruleFormHtml = `
  <section class="issue-card" aria-labelledby="rule-heading">
    <div class="section-heading"><span class="step-label">02 / Rules</span><h2 id="rule-heading">AI Rule Definition</h2></div>
    <p class="helper">Describe a constraint in your own words. Review the interpretation before approving it.</p>
    <form id="rule-form">
      <label for="requirement">Describe an architecture rule</label>
      <textarea id="requirement" rows="4" placeholder="Only PaymentService may depend on PaymentGateway."></textarea>
      <button id="generate" type="submit">Generate Rule</button>
    </form>
    <p id="rule-status" role="status" aria-live="polite">Review the interpretation before approving.</p>
    <div id="validation-errors" class="notice notice-error" role="alert" hidden></div>
    <div id="interpretation-card" class="interpretation-card" hidden>
      <div class="interpretation-heading"><h3>Generated interpretation</h3><span id="rule-badge" class="status-pill">Not generated</span></div>
      <dl id="interpretation" class="key-values"></dl>
    </div>
    <aside id="conflict-card" class="notice notice-warning" role="alert" hidden>
      <h3>Conflict detected</h3><div id="conflicts"></div>
      <p class="helper">Review the conflicts before confirming approval.</p>
      <div class="action-row"><button id="confirm-approval" type="button" disabled>Confirm Approval</button>
        <button id="cancel-conflict" class="secondary" type="button" disabled>Cancel</button></div>
    </aside>
    <button id="approve" type="button" disabled>Approve and save rule</button>
    <details id="raw-output" hidden><summary>Generated output</summary><pre id="generated-text"></pre></details>
  </section>`;

export const architectureStyles = `
  * { box-sizing: border-box; }
  body { background: var(--vscode-editor-background); color: var(--vscode-foreground);
    font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); line-height: 1.5; margin: 0; padding: 20px; }
  main { max-width: 1040px; margin: 0 auto; min-width: 0; }
  .header { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between;
    gap: 12px; margin: 0 auto 20px; max-width: 1040px; }
  .header h1 { font-size: 20px; font-weight: 600; margin: 0 0 4px; letter-spacing: -.2px; }
  .header p, .helper { color: var(--vscode-descriptionForeground); margin: 0 0 12px; font-size: 12px; }
  .backend-status { font-size: 11px; color: var(--vscode-descriptionForeground); border: 1px solid var(--vscode-panel-border);
    border-radius: 20px; padding: 5px 10px; overflow-wrap: anywhere; }
  .issue-card { min-width: 0; border: 1px solid var(--vscode-panel-border); border-radius: 8px;
    background: var(--vscode-editorWidget-background, var(--vscode-editor-background)); padding: 18px; margin-bottom: 16px; }
  .section-heading { margin-bottom: 8px; }
  .section-heading h2 { font-size: 15px; font-weight: 600; margin: 3px 0 0; }
  .step-label { color: var(--vscode-descriptionForeground); text-transform: uppercase; letter-spacing: .8px; font-size: 10px; }
  .action-row, .status-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 12px 0; }
  button { background: var(--vscode-button-background); color: var(--vscode-button-foreground);
    font: inherit; font-size: 12px; border: 1px solid transparent; border-radius: 4px; padding: 7px 12px;
    cursor: pointer; min-height: 32px; max-width: 100%; white-space: normal; overflow-wrap: anywhere; }
  button:hover:enabled { background: var(--vscode-button-hoverBackground); }
  button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
  button.secondary:hover:enabled { background: var(--vscode-button-secondaryHoverBackground); }
  button:disabled { opacity: .55; cursor: default; }
  button:focus-visible, textarea:focus-visible, summary:focus-visible { outline: 1px solid var(--vscode-focusBorder); outline-offset: 2px; }
  .status-pill { display: inline-block; font-size: 11px; line-height: 1.4; border: 1px solid var(--vscode-panel-border);
    background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); border-radius: 20px; padding: 4px 8px; }
  .status-success { border-color: var(--vscode-testing-iconPassed, var(--vscode-panel-border)); }
  .status-warning { border-color: var(--vscode-editorWarning-foreground); }
  .status-error { border-color: var(--vscode-errorForeground); }
  label { display: block; font-weight: 500; margin-top: 12px; }
  textarea { width: 100%; resize: vertical; min-height: 100px; margin: 7px 0 10px; border-radius: 4px;
    padding: 10px; font: inherit; line-height: 1.5; color: var(--vscode-input-foreground); background: var(--vscode-input-background);
    border: 1px solid var(--vscode-input-border, var(--vscode-panel-border)); }
  dl { margin: 12px 0; min-width: 0; }
  dt { color: var(--vscode-descriptionForeground); font-size: 11px; font-weight: 500; }
  dd { margin: 0 0 8px; overflow-wrap: anywhere; white-space: pre-wrap; }
  .project-metrics, .summary-metrics, .key-values { display: grid; grid-template-columns: minmax(95px, auto) minmax(0, 1fr); gap: 5px 14px; }
  .project-metrics dd, .summary-metrics dd, .key-values dd { margin: 0; }
  .summary-metrics { border-block: 1px solid var(--vscode-panel-border); padding: 12px 0; }
  .summary-metrics:empty, .project-metrics:empty { display: none; }
  .interpretation-card { border: 1px solid var(--vscode-panel-border); border-radius: 6px; padding: 14px; margin: 14px 0; }
  .interpretation-heading { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between; }
  h3 { font-size: 13px; margin: 0 0 6px; font-weight: 600; }
  h4 { font-size: 13px; margin: 18px 0 10px; font-weight: 600; overflow-wrap: anywhere; }
  #scan-status, #sync-status, #rule-status, #conformance-status { font-size: 12px; margin: 10px 0; overflow-wrap: anywhere; }
  .notice { padding: 12px; border: 1px solid var(--vscode-panel-border); border-radius: 5px; margin: 12px 0; overflow-wrap: anywhere; }
  .notice-error { border-color: var(--vscode-errorForeground); white-space: pre-wrap; }
  .notice-warning { border-color: var(--vscode-editorWarning-foreground); }
  .conflict-item + .conflict-item { border-top: 1px solid var(--vscode-panel-border); padding-top: 10px; margin-top: 10px; }
  .conflict-item p { margin: 4px 0 8px; }
  .violation-card { border: 1px solid var(--vscode-panel-border); border-radius: 6px; margin: 10px 0; padding: 12px; }
  button.violation-open { display: block; text-align: left; width: 100%; background: transparent; color: var(--vscode-foreground);
    font-weight: 600; padding: 0; min-height: 24px; border: 0; border-radius: 0; }
  button.violation-open:hover:enabled { background: transparent; text-decoration: underline; }
  button.violation-open:disabled { opacity: 1; }
  .severity-error { border-left: 2px solid var(--vscode-errorForeground); }
  .severity-warning { border-left: 2px solid var(--vscode-editorWarning-foreground); }
  .severity-info { border-left: 2px solid var(--vscode-editorInfo-foreground); }
  .violation-card dl { display: grid; grid-template-columns: 70px minmax(0, 1fr); gap: 4px 12px; font-size: 12px; }
  .violation-card dd { margin: 0; }
  button.source-link { background: transparent; color: var(--vscode-textLink-foreground); padding: 0; text-align: left; font-size: 11px; }
  button.source-link:hover:enabled { background: transparent; text-decoration: underline; }
  .current-file-violations { border-left: 2px solid var(--vscode-focusBorder); padding-left: 12px; }
  .other-project-violations > h4 { color: var(--vscode-descriptionForeground); }
  .empty-state { padding: 12px; border: 1px dashed var(--vscode-panel-border); border-radius: 5px; color: var(--vscode-descriptionForeground); }
  .footnote { margin-top: 14px; }
  details { margin-top: 12px; }
  summary { cursor: pointer; font-size: 12px; color: var(--vscode-descriptionForeground); }
  pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 11px; }
  [hidden] { display: none !important; }
  @media (max-width: 440px) {
    body { padding: 10px; }
    .issue-card { padding: 12px; }
    .project-metrics, .summary-metrics, .key-values { grid-template-columns: minmax(0, 1fr); gap: 2px; }
    .project-metrics dd, .summary-metrics dd, .key-values dd { margin-bottom: 7px; }
    .violation-card dl { grid-template-columns: minmax(0, 1fr); }
    .violation-card dd { margin-bottom: 6px; }
  }
`;

export const ruleWebviewScript = `
  const vscode = acquireVsCodeApi();
  const input = document.getElementById('requirement');
  const generate = document.getElementById('generate');
  const approve = document.getElementById('approve');
  const status = document.getElementById('rule-status');
  const interpretation = document.getElementById('interpretation');
  const errors = document.getElementById('validation-errors');
  const conflicts = document.getElementById('conflicts');
  const conflictCard = document.getElementById('conflict-card');
  const confirmApproval = document.getElementById('confirm-approval');
  const cancelConflict = document.getElementById('cancel-conflict');
  const scan = document.getElementById('scan');
  const scanStatus = document.getElementById('scan-status');
  const scanSummary = document.getElementById('scan-summary');
  const sync = document.getElementById('sync');
  const syncStatus = document.getElementById('sync-status');
  const checkConformance = document.getElementById('check-conformance');
  const conformanceStatus = document.getElementById('conformance-status');
  const conformanceSummary = document.getElementById('conformance-summary');
  const violationList = document.getElementById('violation-list');
  let busy = false;
  let analysisBusy = false;
  let syncBusy = false;
  let canSync = false;
  let conformanceBusy = false;
  let canCheck = false;
  let canApprove = false;
  let hasConflicts = false;
  function updateButtons() {
    input.disabled = busy || analysisBusy || syncBusy || conformanceBusy;
    generate.disabled = busy || analysisBusy || syncBusy || conformanceBusy;
    approve.disabled = busy || analysisBusy || syncBusy || conformanceBusy || !canApprove;
    scan.disabled = busy || analysisBusy || syncBusy || conformanceBusy;
    sync.disabled = busy || analysisBusy || syncBusy || conformanceBusy || !canSync;
    checkConformance.disabled = busy || analysisBusy || syncBusy || conformanceBusy || !canCheck;
    confirmApproval.disabled = busy || analysisBusy || syncBusy || conformanceBusy || !canApprove || !hasConflicts;
    cancelConflict.disabled = busy || !hasConflicts;
  }
  function badge(id, text, tone = '') {
    const item = document.getElementById(id);
    item.textContent = text;
    item.className = 'status-pill' + (tone ? ' status-' + tone : '');
  }
  function clearConflicts() {
    hasConflicts = false;
    conflicts.replaceChildren();
    conflictCard.hidden = true;
  }
  function clearProposal() {
    canApprove = false;
    interpretation.replaceChildren();
    errors.textContent = '';
    errors.hidden = true;
    clearConflicts();
    document.getElementById('interpretation-card').hidden = true;
    document.getElementById('generated-text').textContent = '';
    document.getElementById('raw-output').hidden = true;
    updateButtons();
  }
  function field(label, value, parent = interpretation) {
    const name = document.createElement('dt');
    const content = document.createElement('dd');
    name.textContent = label;
    // Entity/scope objects are displayed as readable values; raw output stays in the collapsed details.
    content.textContent = value === undefined ? 'Not supplied' : value === null ? 'Not applicable'
      : typeof value !== 'object' ? String(value)
      : typeof value.name === 'string' ? value.name + (value.entity_type ? ' (' + value.entity_type + ')' : '')
      : typeof value.type === 'string' ? value.type + (value.value == null ? '' : ': ' + String(value.value)) : 'Not supplied';
    parent.append(name, content);
  }
  function showErrors(items) {
    errors.textContent = items.map(item => item.path + ': ' + item.message).join('\\n');
    errors.hidden = items.length === 0;
  }
  function renderViolations(violations, parent, result, state) {
    for (const violation of violations) {
      const card = document.createElement('div');
      card.className = 'violation-card severity-' + violation.severity.toLowerCase();
      const open = document.createElement('button');
      open.type = 'button';
      open.className = 'violation-open';
      open.textContent = violation.severity + ': ' + violation.message;
      open.disabled = !state.navigableViolationIds.includes(violation.violation_id);
      open.addEventListener('click', () => {
        if (!open.disabled) { vscode.postMessage({ type: 'openViolation', violationId: violation.violation_id }); }
      });
      card.append(open);
      const details = document.createElement('dl');
      field('Source', violation.source, details);
      if (violation.relationship) { field('Relationship', violation.relationship, details); }
      if (violation.target) { field('Target', violation.target, details); }
      const metadata = result.rule_metadata[violation.rule_id];
      field('Rule', violation.rule_id + ' (' + metadata.rule_source + ', ' + metadata.rule_type + ')', details);
      if (open.disabled) { field('Source navigation', 'Source file or location unavailable.', details); }
      card.append(details);
      if (violation.file_path) {
        const location = document.createElement('button');
        location.type = 'button';
        location.className = 'source-link';
        location.textContent = 'Open ' + violation.file_path + (violation.start_line ? ':' + violation.start_line : '');
        location.disabled = open.disabled;
        location.addEventListener('click', () => {
          if (!location.disabled) { vscode.postMessage({ type: 'openViolation', violationId: violation.violation_id }); }
        });
        card.append(location);
      }
      parent.append(card);
    }
  }
  function violationSection(title, className) {
    const section = document.createElement('section');
    section.className = className;
    const heading = document.createElement('h4');
    heading.textContent = title;
    section.append(heading);
    violationList.append(section);
    return section;
  }
  scan.addEventListener('click', () => {
    if (busy || analysisBusy || syncBusy || conformanceBusy) { return; }
    analysisBusy = true;
    updateButtons();
    scanStatus.textContent = 'Preparing architecture scan...';
    badge('analysis-badge', 'Analysis: Analyzing');
    vscode.postMessage({ type: 'scan' });
  });
  sync.addEventListener('click', () => {
    if (busy || analysisBusy || syncBusy || conformanceBusy || !canSync) { return; }
    syncBusy = true;
    updateButtons();
    syncStatus.textContent = 'AI context: synchronizing...';
    badge('sync-badge', 'AI Context: Synchronizing');
    vscode.postMessage({ type: 'sync' });
  });
  checkConformance.addEventListener('click', () => {
    if (busy || analysisBusy || syncBusy || conformanceBusy || !canCheck) { return; }
    conformanceBusy = true;
    conformanceStatus.textContent = 'Architecture conformance: checking...';
    badge('conformance-badge', 'Conformance: Checking');
    updateButtons();
    vscode.postMessage({ type: 'checkConformance' });
  });
  document.getElementById('clear-conformance').addEventListener('click', () => vscode.postMessage({ type: 'clearConformance' }));
  input.addEventListener('input', () => {
    clearProposal();
    status.textContent = 'Generate a new interpretation for the edited requirement.';
    vscode.postMessage({ type: 'edit' });
  });
  document.getElementById('rule-form').addEventListener('submit', event => {
    event.preventDefault();
    if (busy || analysisBusy || syncBusy || conformanceBusy) { return; }
    const requirement = input.value.trim();
    clearProposal();
    if (!requirement) { status.textContent = 'Enter an architecture rule first.'; return; }
    busy = true;
    updateButtons();
    status.textContent = 'Generating interpretation...';
    badge('rule-badge', 'Generating');
    vscode.postMessage({ type: 'generate', requirement });
  });
  function requestApproval() {
    if (busy || analysisBusy || syncBusy || conformanceBusy || !canApprove) { return; }
    busy = true;
    updateButtons();
    status.textContent = 'Checking conflicts and approving...';
    vscode.postMessage({ type: 'approve' });
  }
  approve.addEventListener('click', requestApproval);
  // This retries the same host approval workflow, including its native conflict confirmation.
  confirmApproval.addEventListener('click', requestApproval);
  cancelConflict.addEventListener('click', () => {
    if (busy || !hasConflicts) { return; }
    clearConflicts();
    status.textContent = 'Approval cancelled. The rule has not been approved.';
    badge('rule-badge', 'Ready for review');
    updateButtons();
  });
  window.addEventListener('message', event => {
    const message = event.data;
    if (message.type === 'proposalCleared') { clearProposal(); }
    if (message.type === 'generationStarted') { input.value = message.requirement; }
    if (message.type === 'backendStatus') {
      document.getElementById('backend-status').textContent = message.configured
        ? 'AI Backend: Configured' + (message.host ? ' · ' + message.host : '') : 'AI Backend: Configuration required';
    }
    if (message.type === 'analysis') {
      const state = message.state;
      analysisBusy = state.status === 'selecting' || state.status === 'running';
      scanSummary.replaceChildren();
      if (state.status === 'succeeded') {
        field('Project', state.summary.projectName, scanSummary);
        field('Components', state.summary.componentCount, scanSummary);
        field('Relationships', state.summary.relationshipCount, scanSummary);
        field('Context file', state.summary.contextPath, scanSummary);
        scanStatus.textContent = 'Project architecture scan complete.';
        badge('analysis-badge', 'Analysis: Complete', 'success');
      } else {
        scanStatus.textContent = state.status === 'running' ? 'Analyzing Spring Boot architecture...'
          : state.status === 'selecting' ? 'Selecting project...'
          : state.status === 'cancelled' ? 'Architecture analysis cancelled.'
          : state.status === 'failed' ? state.message : 'Scan the opened Java project to generate its local architecture context.';
        badge('analysis-badge', 'Analysis: ' + (analysisBusy ? 'Analyzing' : state.status === 'failed' ? 'Failed'
          : state.status === 'cancelled' ? 'Cancelled' : 'Not analyzed'), state.status === 'failed' ? 'error' : '');
      }
    }
    if (message.type === 'busy') { busy = message.busy; }
    if (message.type === 'conformance') {
      const state = message.state;
      canCheck = message.canCheck;
      conformanceBusy = message.checking;
      conformanceSummary.replaceChildren();
      violationList.replaceChildren();
      if (state.status === 'checked') {
        const result = state.result;
        conformanceStatus.textContent = result.conformant ? 'Architecture conformance: passed (conformant).'
          : 'Architecture conformance: failed (violations found).';
        field('Conformant', result.conformant, conformanceSummary);
        field('Total violations', result.summary.total, conformanceSummary);
        field('Base rule violations', result.summary.base_rule_violations, conformanceSummary);
        field('Custom rule violations', result.summary.custom_rule_violations, conformanceSummary);
        badge('conformance-badge', 'Conformance: ' + (result.conformant ? 'Passed' : result.summary.total + ' violations'), result.conformant ? 'success' : 'warning');
        if (message.activeFile && message.violationGroups) {
          const groups = message.violationGroups;
          const current = violationSection('Current File Violations — ' + message.activeFile.fileName
            + ' (' + groups.currentFileViolations.length + ')', 'current-file-violations');
          if (groups.currentFileViolations.length === 0) {
            const empty = document.createElement('p');
            empty.textContent = 'No architecture violations in this file.';
            empty.className = 'empty-state';
            current.append(empty);
          }
          renderViolations(groups.currentFileViolations, current, result, state);
          if (groups.otherViolations.length) {
            const other = violationSection('Other Project Violations (' + groups.otherViolations.length + ')', 'other-project-violations');
            renderViolations(groups.otherViolations, other, result, state);
          }
        } else { renderViolations(result.violations, violationList, result, state); }
      } else {
        conformanceStatus.textContent = state.status === 'checking' ? 'Architecture conformance: checking...'
          : state.status === 'stale' ? 'Architecture conformance: stale / not checked. ' + (state.message || '')
          : state.status === 'failed' ? 'Architecture conformance: check failed. ' + state.message
          : state.status === 'cancelled' ? 'Architecture conformance: cancelled.'
          : 'Architecture conformance: not checked. ' + (state.message || 'Analyze and sync a project first.');
        badge('conformance-badge', 'Conformance: ' + (state.status === 'checking' ? 'Checking'
          : state.status === 'failed' ? 'Check failed' : state.status === 'stale' ? 'Stale' : 'Not checked'), state.status === 'failed' ? 'error' : '');
      }
    }
    if (message.type === 'contextSync') {
      const state = message.state;
      canSync = message.canSync;
      syncBusy = message.syncing;
      syncStatus.textContent = state.status === 'synchronized'
        ? 'AI context: synchronized. ' + state.response.project_name + ': ' + state.response.components
          + ' components, ' + state.response.relationships + ' relationships.'
        : state.status === 'syncing' ? 'AI context: synchronizing...'
        : 'AI context: not synchronized.' + (state.message ? ' ' + state.message : '');
      badge('sync-badge', 'AI Context: ' + (state.status === 'synchronized' ? 'Synchronized'
        : state.status === 'syncing' ? 'Synchronizing' : 'Not synchronized'), state.status === 'synchronized' ? 'success' : state.status === 'failed' ? 'warning' : '');
    }
    if (message.type === 'contextChanged') {
      clearProposal();
      status.textContent = 'Project context updated. Generate a new interpretation.';
    }
    if (message.type === 'proposal') {
      const response = message.response;
      clearProposal();
      canApprove = message.canApprove;
      const envelope = response.rule;
      if (envelope && typeof envelope === 'object' && !Array.isArray(envelope)) {
        field('Status', envelope.status ?? 'Unknown');
        if (envelope.status === 'VALID' && envelope.rule && typeof envelope.rule === 'object') {
          const rule = envelope.rule;
          field('Rule type', rule.rule_type);
          field('Source', rule.source);
          field('Relationship', rule.relationship);
          field('Target', rule.target);
          field('Action', rule.action);
          field('Scope', rule.scope);
          field('Exception', rule.is_exception);
        } else { field('Reason code', envelope.reason_code ?? 'Not supplied'); }
      }
      showErrors(response.validation_errors);
      document.getElementById('interpretation-card').hidden = false;
      badge('rule-badge', canApprove ? 'Ready for review' : response.schema_valid ? 'Needs clarification' : 'Validation failed', canApprove ? 'success' : 'warning');
      status.textContent = !response.json_valid ? 'The model did not return valid JSON.'
        : !response.schema_valid ? 'The interpretation failed backend validation. Generate another interpretation.'
        : canApprove ? 'Review the interpretation, then approve to save it.' : 'This interpretation cannot be approved.';
      document.getElementById('generated-text').textContent = response.generated_text;
      document.getElementById('raw-output').hidden = false;
    }
    if (message.type === 'conflicts') {
      clearConflicts();
      hasConflicts = message.conflicts.conflicts.length > 0;
      conflictCard.hidden = !hasConflicts;
      for (const conflict of message.conflicts.conflicts) {
        const card = document.createElement('div');
        card.className = 'conflict-item';
        const identifier = document.createElement('strong');
        identifier.textContent = conflict.existing_rule_id;
        const reason = document.createElement('p');
        reason.textContent = conflict.reason;
        card.append(identifier, reason);
        conflicts.append(card);
      }
      badge('rule-badge', 'Conflict detected', 'warning');
    }
    if (message.type === 'cancelled') {
      canApprove = message.canApprove;
      status.textContent = 'Approval cancelled. The rule has not been approved.';
    }
    if (message.type === 'approved') {
      canApprove = false;
      const result = message.approval;
      status.textContent = result.duplicate ? 'Already approved as ' + result.rule_id + '. No duplicate was saved.'
        : 'Approved and saved as ' + result.rule_id + (result.conflicts_confirmed ? ' with explicit conflict confirmation.' : '.');
      clearConflicts();
      badge('rule-badge', result.duplicate ? 'Duplicate rule' : 'Approved', 'success');
    }
    if (message.type === 'error') {
      canApprove = message.canApprove;
      status.textContent = message.message;
      showErrors(message.errors);
      badge('rule-badge', 'Request failed', 'error');
    }
    updateButtons();
  });
  // Recover the latest scan result when a panel is reopened or first loads during a scan.
  vscode.postMessage({ type: 'ready' });
`;
