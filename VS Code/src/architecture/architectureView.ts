export const analysisFormHtml = `
  <section class="issue-card" aria-labelledby="analysis-heading">
    <h3 id="analysis-heading">Project architecture</h3>
    <button id="scan" type="button">Scan Project Architecture</button>
    <p id="scan-status" role="status" aria-live="polite">Scan the opened Java project to generate its local architecture context.</p>
    <dl id="scan-summary"></dl>
    <button id="sync" type="button" disabled>Sync Project Context</button>
    <p id="sync-status" role="status" aria-live="polite">AI context: not synchronized.</p>
    <p>After scanning, sync architecture metadata to use this project for AI rule generation.</p>
  </section>`;

export const conformanceFormHtml = `
  <section class="issue-card" aria-labelledby="conformance-heading">
    <h3 id="conformance-heading">Architecture conformance</h3>
    <button id="check-conformance" type="button" disabled>Check Architecture Conformance</button>
    <button id="clear-conformance" type="button">Clear results</button>
    <p id="conformance-status" role="status" aria-live="polite">Architecture conformance: not checked.</p>
    <dl id="conformance-summary"></dl>
    <div id="violation-list"></div>
    <p>Architecture violations are determined by the deterministic conformance engine, not by the LLM.</p>
  </section>`;

export const ruleFormHtml = `
  <section class="issue-card" aria-labelledby="rule-heading">
    <h3 id="rule-heading">Architecture rules</h3>
    <form id="rule-form">
      <label for="requirement">Describe an architecture rule</label>
      <textarea id="requirement" placeholder="Only PaymentService may depend on PaymentGateway."></textarea>
      <button id="generate" type="submit">Generate interpretation</button>
    </form>
    <p id="rule-status" role="status" aria-live="polite">Review the interpretation before approving.</p>
    <div id="validation-errors" role="alert"></div>
    <dl id="interpretation"></dl>
    <div id="conflicts" role="alert"></div>
    <button id="approve" type="button" disabled>Approve and save rule</button>
    <details id="raw-output" hidden><summary>Generated output</summary><pre id="generated-text"></pre></details>
  </section>`;

export const ruleWebviewScript = `
  const vscode = acquireVsCodeApi();
  const input = document.getElementById('requirement');
  const generate = document.getElementById('generate');
  const approve = document.getElementById('approve');
  const status = document.getElementById('rule-status');
  const interpretation = document.getElementById('interpretation');
  const errors = document.getElementById('validation-errors');
  const conflicts = document.getElementById('conflicts');
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
  function updateButtons() {
    input.disabled = busy || analysisBusy || syncBusy || conformanceBusy;
    generate.disabled = busy || analysisBusy || syncBusy || conformanceBusy;
    approve.disabled = busy || analysisBusy || syncBusy || conformanceBusy || !canApprove;
    scan.disabled = busy || analysisBusy || syncBusy || conformanceBusy;
    sync.disabled = busy || analysisBusy || syncBusy || conformanceBusy || !canSync;
    checkConformance.disabled = busy || analysisBusy || syncBusy || conformanceBusy || !canCheck;
  }
  function clearProposal() {
    canApprove = false;
    interpretation.replaceChildren();
    errors.textContent = '';
    conflicts.textContent = '';
    document.getElementById('generated-text').textContent = '';
    document.getElementById('raw-output').hidden = true;
    updateButtons();
  }
  function field(label, value, parent = interpretation) {
    const name = document.createElement('dt');
    const content = document.createElement('dd');
    name.textContent = label;
    content.textContent = value === undefined ? 'Not supplied' : typeof value === 'string' ? value : JSON.stringify(value);
    parent.append(name, content);
  }
  function showErrors(items) {
    errors.textContent = items.map(item => item.path + ': ' + item.message).join('\\n');
  }
  function renderViolations(violations, parent, result, state) {
    for (const violation of violations) {
      const card = document.createElement('div');
      const open = document.createElement('button');
      open.type = 'button';
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
      if (violation.file_path) { field('Location', violation.file_path + (violation.start_line ? ':' + violation.start_line : ''), details); }
      if (open.disabled) { field('Source navigation', 'Source file or location unavailable.', details); }
      card.append(details);
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
    vscode.postMessage({ type: 'scan' });
  });
  sync.addEventListener('click', () => {
    if (busy || analysisBusy || syncBusy || conformanceBusy || !canSync) { return; }
    syncBusy = true;
    updateButtons();
    syncStatus.textContent = 'AI context: synchronizing...';
    vscode.postMessage({ type: 'sync' });
  });
  checkConformance.addEventListener('click', () => {
    if (busy || analysisBusy || syncBusy || conformanceBusy || !canCheck) { return; }
    conformanceBusy = true;
    conformanceStatus.textContent = 'Architecture conformance: checking...';
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
    vscode.postMessage({ type: 'generate', requirement });
  });
  approve.addEventListener('click', () => {
    if (busy || analysisBusy || syncBusy || conformanceBusy || !canApprove) { return; }
    busy = true;
    updateButtons();
    status.textContent = 'Checking conflicts and approving...';
    vscode.postMessage({ type: 'approve' });
  });
  window.addEventListener('message', event => {
    const message = event.data;
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
      } else {
        scanStatus.textContent = state.status === 'running' ? 'Analyzing Spring Boot architecture...'
          : state.status === 'selecting' ? 'Selecting project...'
          : state.status === 'cancelled' ? 'Architecture analysis cancelled.'
          : state.status === 'failed' ? state.message : 'Scan the opened Java project to generate its local architecture context.';
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
        if (message.activeFile && message.violationGroups) {
          const groups = message.violationGroups;
          const current = violationSection('Current File Violations — ' + message.activeFile.fileName
            + ' (' + groups.currentFileViolations.length + ')', 'current-file-violations');
          if (groups.currentFileViolations.length === 0) {
            const empty = document.createElement('p');
            empty.textContent = 'No architecture violations in this file.';
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
      status.textContent = !response.json_valid ? 'The model did not return valid JSON.'
        : !response.schema_valid ? 'The interpretation failed backend validation. Generate another interpretation.'
        : canApprove ? 'Review the interpretation, then approve to save it.' : 'This interpretation cannot be approved.';
      document.getElementById('generated-text').textContent = response.generated_text;
      document.getElementById('raw-output').hidden = false;
    }
    if (message.type === 'conflicts') {
      conflicts.textContent = message.conflicts.conflicts.map(item => item.existing_rule_id + ': ' + item.reason).join('\\n');
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
    }
    if (message.type === 'error') {
      canApprove = message.canApprove;
      status.textContent = message.message;
      showErrors(message.errors);
    }
    updateButtons();
  });
  // Recover the latest scan result when a panel is reopened or first loads during a scan.
  vscode.postMessage({ type: 'ready' });
`;
