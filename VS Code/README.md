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
