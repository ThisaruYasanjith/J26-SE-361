import { spawn } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { Readable } from 'node:stream';
import { isProjectContext, ProjectContext } from './contracts';

export interface WorkspaceProject { name: string; fsPath: string; scheme: string; }
export interface AnalysisSummary {
  projectRoot: string;
  contextPath: string;
  projectName: string;
  componentCount: number;
  relationshipCount: number;
}
export interface AnalyzerLog { appendLine(message: string): void; }
export class AnalyzerError extends Error {
  constructor(public readonly kind: 'workspace' | 'project' | 'jar-missing' | 'java-unavailable' | 'execution' | 'context' | 'permissions',
    message: string, public readonly details?: string) { super(message); this.name = 'AnalyzerError'; }
}
export class AnalysisCancelled extends Error {
  constructor() { super('Architecture analysis cancelled.'); this.name = 'AnalysisCancelled'; }
}
export async function selectWorkspace(
  folders: readonly WorkspaceProject[] | undefined,
  choose: (folders: readonly WorkspaceProject[]) => Promise<WorkspaceProject | undefined>,
): Promise<WorkspaceProject> {
  if (!folders?.length) { throw new AnalyzerError('workspace', 'Open a Java project folder in VS Code before scanning.'); }
  if (folders.length === 1) { return folders[0]; }
  const selected = await choose(folders);
  if (!selected) { throw new AnalysisCancelled(); }
  if (!folders.includes(selected)) { throw new AnalyzerError('workspace', 'Choose one of the opened workspace folders.'); }
  return selected;
}

export interface AnalyzerFiles {
  stat(file: string): Promise<{ isFile(): boolean; isDirectory(): boolean }>;
  realpath(file: string): Promise<string>;
  readFile(file: string, encoding: 'utf8'): Promise<string>;
}
const localFiles: AnalyzerFiles = {
  stat: file => fs.stat(file), realpath: file => fs.realpath(file), readFile: file => fs.readFile(file, 'utf8'),
};
async function inspect(file: string, files: AnalyzerFiles) {
  try { return await files.stat(file); } catch (error) {
    if (['ENOENT', 'ENOTDIR'].includes((error as NodeJS.ErrnoException).code ?? '')) { return undefined; }
    throw error;
  }
}
export async function resolveAnalyzerJar(extensionRoot: string, files: AnalyzerFiles = localFiles): Promise<string> {
  const candidates = [
    path.resolve(extensionRoot, '..', 'Architecture', 'java-analyzer', 'target', 'java-analyzer.jar'),
    path.resolve(extensionRoot, 'dist', 'java-analyzer.jar'),
  ];
  // Prefer the current Maven build in a source checkout; installed extensions use the bundled copy.
  for (const candidate of candidates) {
    if ((await inspect(candidate, files))?.isFile()) { return candidate; }
  }
  throw new AnalyzerError('jar-missing',
    'Java analyzer JAR not found. Build Architecture/java-analyzer with mvn package, then scan again. Packaged extensions need dist/java-analyzer.jar.',
    `Checked: ${candidates.join(', ')}`);
}

export interface JavaRunRequest { jarPath: string; projectRoot: string; signal?: AbortSignal; }
export interface JavaRunResult { exitCode: number | null; signal: NodeJS.Signals | null; stdout: string; stderr: string; }
export interface AnalyzerChild {
  stdout: Readable;
  stderr: Readable;
  kill(signal?: NodeJS.Signals | number): boolean;
  once(event: 'error', listener: (error: Error) => void): unknown;
  once(event: 'close', listener: (code: number | null, signal: NodeJS.Signals | null) => void): unknown;
}
export type StartJava = (args: string[], cwd: string) => AnalyzerChild;
const startJava: StartJava = (args, cwd) => spawn('java', args, {
  cwd, shell: false, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
});
export function runJavaAnalyzer(request: JavaRunRequest, start: StartJava = startJava): Promise<JavaRunResult> {
  if (request.signal?.aborted) { return Promise.reject(new AnalysisCancelled()); }
  return new Promise((resolve, reject) => {
    let child: AnalyzerChild;
    let stdout = '';
    let stderr = '';
    let killTimer: ReturnType<typeof setTimeout> | undefined;
    const maximumOutput = 64 * 1024;
    const stop = () => {
      child.kill('SIGTERM');
      killTimer = setTimeout(() => child.kill('SIGKILL'), 3000);
      killTimer.unref();
    };
    const cleanup = () => { request.signal?.removeEventListener('abort', stop); clearTimeout(killTimer); };
    const fail = (error: Error) => {
      cleanup();
      if (request.signal?.aborted) { reject(new AnalysisCancelled()); return; }
      const code = (error as NodeJS.ErrnoException).code;
      reject(new AnalyzerError(code === 'ENOENT' ? 'java-unavailable' : 'execution', code === 'ENOENT'
        ? 'Java is required to run the architecture analyzer. Ensure Java 17 or newer is available on PATH.'
        : 'Could not start the Java architecture analyzer. Check the Architecture Governance output.', `${code ?? ''}: ${error.message}`));
    };
    try {
      // Separate arguments preserve spaces and shell characters in project paths.
      child = start(['-jar', request.jarPath, request.projectRoot], request.projectRoot);
      child.stdout.setEncoding('utf8');
      child.stderr.setEncoding('utf8');
      child.stdout.on('data', (chunk: string) => { stdout = (stdout + chunk).slice(0, maximumOutput); });
      child.stderr.on('data', (chunk: string) => { stderr = (stderr + chunk).slice(0, maximumOutput); });
      child.once('error', fail);
      child.once('close', (exitCode: number | null, signal: NodeJS.Signals | null) => {
        cleanup();
        if (request.signal?.aborted) { reject(new AnalysisCancelled()); }
        else { resolve({ exitCode, signal, stdout, stderr }); }
      });
      request.signal?.addEventListener('abort', stop, { once: true });
      if (request.signal?.aborted) { stop(); }
    } catch (error) { fail(error as Error); }
  });
}

function inside(root: string, candidate: string): boolean {
  const relative = path.relative(root, candidate);
  return relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

export async function readProjectContext(projectRoot: string, files: AnalyzerFiles = localFiles): Promise<ProjectContext> {
  const contextPath = path.join(projectRoot, '.architecture', 'project_context.json');
  try {
    if (!(await inspect(contextPath, files))?.isFile()) {
      throw new AnalyzerError('context', 'Project context file is missing. Scan Project Architecture first.');
    }
    if (!inside(await files.realpath(projectRoot), await files.realpath(contextPath))) {
      throw new AnalyzerError('context', 'The project context points outside the selected workspace.');
    }
    const context: unknown = JSON.parse(await files.readFile(contextPath, 'utf8'));
    if (!isProjectContext(context)) {
      throw new AnalyzerError('context', 'The project_context.json has an unsupported version or missing project/array fields.');
    }
    return context;
  } catch (error) {
    if (error instanceof AnalyzerError) { throw error; }
    if (error instanceof SyntaxError) { throw new AnalyzerError('context', 'The project_context.json is not valid JSON.'); }
    const code = (error as NodeJS.ErrnoException).code;
    throw new AnalyzerError('permissions', 'Cannot read project_context.json. Check file permissions and Architecture Governance output.', `${code ?? ''}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

export class AnalyzerRunner {
  constructor(private readonly extensionRoot: string, private readonly output: AnalyzerLog,
    private readonly execute: (request: JavaRunRequest) => Promise<JavaRunResult> = runJavaAnalyzer,
    private readonly files: AnalyzerFiles = localFiles) {}

  async analyze(project: WorkspaceProject, signal?: AbortSignal): Promise<AnalysisSummary> {
    try {
      if (signal?.aborted) { throw new AnalysisCancelled(); }
      if (project.scheme !== 'file' || !path.isAbsolute(project.fsPath)) {
        throw new AnalyzerError('workspace', 'Open a local filesystem project folder to run the Java analyzer.');
      }
      const projectRoot = path.resolve(project.fsPath);
      this.output.appendLine(`Selected workspace: ${projectRoot}`);
      if (!(await inspect(projectRoot, this.files))?.isDirectory()) {
        throw new AnalyzerError('project', 'The selected workspace folder is missing or is not a directory.');
      }
      const markers = await Promise.all(['pom.xml', 'build.gradle', 'build.gradle.kts'].map(file => inspect(path.join(projectRoot, file), this.files)));
      const sourceRoot = path.join(projectRoot, 'src', 'main', 'java');
      const sources = await inspect(sourceRoot, this.files);
      if (!markers.some(marker => marker?.isFile()) && !sources?.isDirectory()) {
        throw new AnalyzerError('project', 'This folder does not look like a Java project. Open its project root containing pom.xml, build.gradle, build.gradle.kts or src/main/java.');
      }
      const canonicalRoot = await this.files.realpath(projectRoot);
      const contextPath = path.join(projectRoot, '.architecture', 'project_context.json');
      // Refuse linked source/output roots that would escape the selected workspace.
      for (const candidate of [sourceRoot, path.dirname(contextPath), contextPath]) {
        if (await inspect(candidate, this.files)) {
          if (!inside(canonicalRoot, await this.files.realpath(candidate))) {
            throw new AnalyzerError('project', 'The project source or context path points outside the selected workspace.');
          }
        }
      }
      const jarPath = await resolveAnalyzerJar(this.extensionRoot, this.files);
      this.output.appendLine(`Analyzer JAR: ${jarPath}`);
      if (signal?.aborted) { throw new AnalysisCancelled(); }
      this.output.appendLine('Starting Java architecture analyzer.');
      const result = await this.execute({ jarPath, projectRoot, signal });
      this.output.appendLine(`Analyzer exit code: ${result.exitCode ?? 'none'}${result.signal ? ` (${result.signal})` : ''}`);
      for (const line of result.stdout.split(/\r?\n/)) {
        if (/^(Project:|Java files found:|Successfully parsed:|Parse failures:|Architecture entities extracted:|Architecture relationships extracted:)/.test(line)) {
          this.output.appendLine(line);
        }
      }
      if (signal?.aborted) { throw new AnalysisCancelled(); }
      if (result.exitCode !== 0) {
        if (result.stderr.trim()) { this.output.appendLine(`Analyzer stderr:\n${result.stderr.trim()}`); }
        throw new AnalyzerError('execution', 'The Java analyzer failed. See Architecture Governance output for details.');
      }
      if (!(await inspect(contextPath, this.files))?.isFile()) {
        throw new AnalyzerError('context', 'The analyzer finished but did not generate .architecture/project_context.json.');
      }
      const context = await readProjectContext(projectRoot, this.files);
      this.output.appendLine(`Generated project context: ${contextPath}`);
      return { projectRoot, contextPath, projectName: context.project_name,
        componentCount: context.components.length, relationshipCount: context.relationships.length };
    } catch (error) {
      if (error instanceof AnalysisCancelled) { this.output.appendLine(error.message); throw error; }
      if (error instanceof AnalyzerError) { this.output.appendLine(error.details ?? error.message); throw error; }
      const code = (error as NodeJS.ErrnoException).code;
      this.output.appendLine(`Analyzer error: ${error instanceof Error ? error.message : String(error)}`);
      throw new AnalyzerError(['EACCES', 'EPERM'].includes(code ?? '') ? 'permissions' : 'execution',
        ['EACCES', 'EPERM'].includes(code ?? '') ? 'Cannot access project or analyzer files. Check file permissions and Architecture Governance output.'
          : 'Architecture analysis failed. See Architecture Governance output for details.');
    }
  }
}
