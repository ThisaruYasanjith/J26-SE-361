## Architecture AI backend integration

Set `architectureGovernance.aiBackendUrl` in VS Code Settings. Its default is `http://127.0.0.1:8000`; a remote HTTPS base URL is also supported, including a path prefix. Requests run in the extension host using built-in `fetch`, not inside the webview. Use a base URL without credentials, query parameters or fragments. Authentication and tunnel setup are outside this commit.

Open **Architecture** from Analysis Modules, or run **Open Architecture Analysis**. Enter a natural-language rule and select **Generate interpretation**. The panel displays the backend status, rule fields, reason code, validation errors and generated text. Only JSON/schema-valid `VALID` interpretations enable **Approve and save rule**. Editing the input requires another generation.

Approval calls the backend conflict check first. Conflicts are displayed in the panel and in a native confirmation dialog. **Approve anyway** is the only action that sends `confirm_conflicts: true`; cancelling leaves the rule unapproved. A conflict reported during the final approval request is handled the same way. Duplicate approval displays the existing rule ID without creating a second copy. Changing the backend URL requires regenerating the interpretation before approval.

Generation uses `POST /rules/generate` with `{requirement, use_rag: true}`. Conflict checking and approval send the complete parsed rule envelope from the generation response's `rule` field to `/rules/check-conflicts` and `/rules/approve`. The extension does not generate IDs, validate architecture semantics, infer conflicts, or persist rules locally.

Network requests show progress and have a five-minute timeout to allow lazy model loading. Approval is never retried automatically after a network failure. Check the **Architecture Governance** Output channel for request URLs, HTTP status, validation summaries and conflict IDs. It does not log submitted requirements, complete generated text or retrieved project documents. Closing the panel aborts its pending client requests; the backend may already be processing a request.

The backend must already be running with its project context configured. This commit does not execute Java analysis, synchronize project context, add architecture diagnostics or deploy a GPU backend. The existing architecture example card and other prototype panels remain available.

From the `VS Code` folder, run `npm run test:architecture` for the mocked client/workflow/webview tests, and `npm run compile` for type-checking, lint and bundling. These unit tests use Node's built-in test runner and do not need a FastAPI server, Qwen download or VS Code GUI. The existing `npm test` command still runs the Electron extension-host tests separately. To review the UI manually, press F5, open Architecture, configure the service URL, and exercise generation, approval, conflict cancellation and explicit override.

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
