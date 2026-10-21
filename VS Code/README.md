## Architecture AI backend integration

Set `architectureGovernance.aiBackendUrl` in VS Code Settings. Its default is `http://127.0.0.1:8000`; a remote HTTPS base URL is also supported, including a path prefix. Requests run in the extension host using built-in `fetch`, not inside the webview. Use a base URL without credentials, query parameters or fragments. Authentication and tunnel setup are outside this commit.

Open **Architecture** from Analysis Modules, or run **Open Architecture Analysis**. Enter a natural-language rule and select **Generate interpretation**. The panel displays the backend status, rule fields, reason code, validation errors and generated text. Only JSON/schema-valid `VALID` interpretations enable **Approve and save rule**. Editing the input requires another generation.

Approval calls the backend conflict check first. Conflicts are displayed in the panel and in a native confirmation dialog. **Approve anyway** is the only action that sends `confirm_conflicts: true`; cancelling leaves the rule unapproved. A conflict reported during the final approval request is handled the same way. Duplicate approval displays the existing rule ID without creating a second copy. Changing the backend URL requires regenerating the interpretation before approval.

Generation uses `POST /rules/generate` with `{requirement, use_rag: true}`. Conflict checking and approval send the complete parsed rule envelope from the generation response's `rule` field to `/rules/check-conflicts` and `/rules/approve`. The extension does not generate IDs, validate architecture semantics, infer conflicts, or persist rules locally.

Network requests show progress and have a five-minute timeout to allow lazy model loading. Approval is never retried automatically after a network failure. Check the **Architecture Governance** Output channel for request URLs, HTTP status, validation summaries and conflict IDs. It does not log submitted requirements, complete generated text or retrieved project documents. Closing the panel aborts its pending rule requests; the backend may already be processing a request. Project synchronization retains its progress/result when the panel is reopened.

The backend must already be running. Scan the Java project locally, then select **Sync Project Context** to supply its context before generating project-specific rules. Other prototype panels remain available.

From the `VS Code` folder, run `npm run test:architecture` for the mocked client/workflow/webview tests, and `npm run compile` for type-checking, lint and bundling. These unit tests use Node's built-in test runner and do not need a FastAPI server, Qwen download or VS Code GUI. The existing `npm test` command still runs the Electron extension-host tests separately. To review the UI manually, press F5, open Architecture, configure the service URL, and exercise generation, approval, conflict cancellation and explicit override.

## Local Java architecture scanning

Build the existing analyzer once with `mvn package` from `Architecture/java-analyzer`. Java 17 or newer must be available as `java` on the extension host's PATH. The extension does not download a JDK or run Maven for you.

Open a Java/Spring Boot project root in VS Code, then use **Scan Project Architecture** in the Architecture panel or **Architecture Governance: Analyze Project Architecture** from the Command Palette. A single workspace folder is used directly; multiple folders prompt for a selection. Cancelling the selection starts no process. Open a local filesystem folder containing `pom.xml`, `build.gradle`, `build.gradle.kts` or `src/main/java`. The extension does not search for project roots outside the selected workspace or automatically descend into nested Maven modules.

The runner invokes `java -jar <analyzer-jar> <selected-project-root>` asynchronously with separate arguments and no shell. Paths containing spaces are supported. The progress notification can cancel the Java process; cancellation is reported separately from failure. Repeated panel/palette actions share one active scan. Closing and reopening the Architecture panel restores the current scan state or latest result.

After exit code zero, the extension reads `<selected-project-root>/.architecture/project_context.json`. It checks schema version `1.0`, non-blank project name/root and component/relationship arrays, then displays the project name, both counts and the context path. These are lightweight checks, not a second full JSON Schema validator. A non-zero analyzer exit is treated as failure even if the Java analyzer wrote a partial context. Linked source/context roots that resolve outside the selected workspace are rejected.

The **Architecture Governance** Output channel records the selected folder, JAR path, process start/exit, stdout summary, failure stderr and generated context path. Missing Java, missing JARs, invalid output and permission errors produce concise messages. Full per-entity stdout is not logged; captured stdout/stderr are bounded to 64 KiB each.

In a monorepo checkout, the runner uses `../Architecture/java-analyzer/target/java-analyzer.jar` relative to the extension folder. Installed extensions use `dist/java-analyzer.jar`. `npm run package` copies the existing Maven artifact into `dist` for inclusion in the extension package and fails clearly if it is unavailable; `npm run compile` does not require the JAR. No binary or Java dependencies are added to the npm lockfile.

Scanning updates local context only. Use the separate synchronization action below to refresh the AI backend. Conformance checks and violation diagnostics remain deferred.

Normal `npm run test:architecture` tests mock Java execution and require neither Java nor Maven. An optional real-analyzer test runs on an isolated temporary copy of an existing demo's `src` directory:

```powershell
$env:RUN_ANALYZER_INTEGRATION = '1'
$env:ANALYZER_DEMO_PROJECT = '../architecture-demo-project'
npm run test:analyzer-integration
Remove-Item Env:RUN_ANALYZER_INTEGRATION
Remove-Item Env:ANALYZER_DEMO_PROJECT
```

The integration test requires a built JAR and Java on PATH. It prints the real analyzer summary and removes its temporary project afterward.

## Syncing the analyzed project to the AI backend

1. Scan the selected Java/Spring Boot project successfully.
2. Select **Sync Project Context** in the Architecture panel. This rereads that analyzed folder's `.architecture/project_context.json` without rerunning Java. It sends the parsed metadata to `PUT /context/project` at the configured backend URL, including any URL path prefix.
3. Wait for **AI context: synchronized**, with the project name and actual component/relationship counts. A failed sync shows **AI context: not synchronized** and a concise error while keeping the successful scan summary visible. Correct the file/service/configuration and retry the button.
4. Generate and review a rule normally. The backend rebuilds RAG on the next retrieval using this project, base rules and approved custom rules. Qwen is reused; synchronization does not reload it. A successful sync clears any pending interpretation, which should be generated again against the new context.

The sync button becomes available after a successful scan. It is an explicit network action; scanning never uploads automatically. Scanning another project or changing `architectureGovernance.aiBackendUrl` clears synchronization status. The status reflects this extension's last successful sync acknowledgement, not a live subscription to backend changes. If the backend restarts or another client replaces its context, sync again. An interrupted/timed-out request may have reached the backend; retrying replaces the context again without adding duplicate entries.

Missing or malformed context files stop before uploading. The backend performs full validation with its existing context models; HTTP 4xx/5xx, unreachable services and timeouts are reported independently of analysis. The Output channel logs the project name, counts, request URL, HTTP status, RAG invalidation acknowledgement and failure details, without logging full context or source code.

The research backend has **one active project context for one developer/project at a time**, with one service worker/writer process. Syncing a different project replaces that context and preserves the shared approved-rule store. Production deployment should scope context, rules and indexes per project/session/user. Set backend `PROJECT_CONTEXT_PATH` to a writable location for the synchronized file. Multi-user isolation is deferred.

## Project Structure

```text
ui-prototype/
├── .vscode/
│   ├── launch.json                  # VS Code debug configurations
│   ├── settings.json                # Project-specific editor settings
│   └── tasks.json                   # Build and watch task definitions
├── dist/                            # Compiled JS output (auto-generated)
├── node_modules/                    # Project dependencies
├── src/
│   ├── extension.ts                 # Main extension entry point & command registration
│   ├── dashboardView.ts             # Sidebar launcher buttons (TreeDataProvider)
│   ├── architecture/
│   │   └── architecturePanel.ts     # Member 1: Architectural analysis Webview
│   ├── codeQuality/
│   │   └── codeQualityPanel.ts      # Member 2: Code quality & smells Webview
│   ├── behavioural/
│   │   └── behaviouralPanel.ts      # Member 3: Behavioural & concurrency Webview
│   └── runtime/
│       └── runtimePanel.ts          # Member 4: Runtime error Webview
├── .gitignore                       # Git ignore rules
├── .vscodeignore                   # Files excluded from the packaged extension
├── esbuild.js                       # esbuild bundler configuration script
├── package.json                     # Extension manifest & command contributions
├── tsconfig.json                    # TypeScript compiler options
└── README.md                        # Documentation

## Prerequisites

## Ensure you have the following installed on your machine:

    1. Node.js (version 18.x or higher)
    2. npm (bundled with Node.js)
    3. Visual Studio Code

## Installation & Setup

    Clone or open the repository folder in VS Code.
    Install the necessary project dependencies by running: npm install

## Build and Run Instructions ## Build the extension

  npm run compile

## Launch the Extension Development Host

  code --extensionDevelopmentPath="$PWD"
