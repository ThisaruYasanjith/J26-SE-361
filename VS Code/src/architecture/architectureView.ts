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
  let busy = false;
  let analysisBusy = false;
  let syncBusy = false;
  let canSync = false;
  let canApprove = false;
  function updateButtons() {
    input.disabled = busy || analysisBusy || syncBusy;
    generate.disabled = busy || analysisBusy || syncBusy;
    approve.disabled = busy || analysisBusy || syncBusy || !canApprove;
    scan.disabled = busy || analysisBusy || syncBusy;
    sync.disabled = busy || analysisBusy || syncBusy || !canSync;
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
  scan.addEventListener('click', () => {
    if (busy || analysisBusy || syncBusy) { return; }
    analysisBusy = true;
    updateButtons();
    scanStatus.textContent = 'Preparing architecture scan...';
    vscode.postMessage({ type: 'scan' });
  });
  sync.addEventListener('click', () => {
    if (busy || analysisBusy || syncBusy || !canSync) { return; }
    syncBusy = true;
    updateButtons();
    syncStatus.textContent = 'AI context: synchronizing...';
    vscode.postMessage({ type: 'sync' });
  });
  input.addEventListener('input', () => {
    clearProposal();
    status.textContent = 'Generate a new interpretation for the edited requirement.';
    vscode.postMessage({ type: 'edit' });
  });
  document.getElementById('rule-form').addEventListener('submit', event => {
    event.preventDefault();
    if (busy || analysisBusy || syncBusy) { return; }
    const requirement = input.value.trim();
    clearProposal();
    if (!requirement) { status.textContent = 'Enter an architecture rule first.'; return; }
    busy = true;
    updateButtons();
    status.textContent = 'Generating interpretation...';
    vscode.postMessage({ type: 'generate', requirement });
  });
  approve.addEventListener('click', () => {
    if (busy || analysisBusy || syncBusy || !canApprove) { return; }
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
