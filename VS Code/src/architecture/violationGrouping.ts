import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { ArchitectureViolation } from './contracts';

export interface ActiveJavaFile { filePath: string; fileName: string; }
export interface ActiveEditorDocument {
  languageId: string;
  isUntitled: boolean;
  uri: { scheme: string; fsPath: string };
}
export interface ViolationGroups {
  currentFileViolations: ArchitectureViolation[];
  otherViolations: ArchitectureViolation[];
}

export function normalizeViolationPath(value: unknown, platform = process.platform): string | undefined {
  if (typeof value !== 'string' || !value || value.includes('\0') || value.includes(':')
    || path.posix.isAbsolute(value) || path.win32.isAbsolute(value)) { return undefined; }
  const normalized = path.posix.normalize(value.replace(/\\/g, '/'));
  if (normalized === '.' || normalized === '..' || normalized.startsWith('../')) { return undefined; }
  return platform === 'win32' ? normalized.toLowerCase() : normalized;
}

export async function activeProjectJavaFile(projectRoot: string, document: ActiveEditorDocument | undefined,
  realpath: (file: string) => Promise<string> = fs.realpath, platform = process.platform): Promise<ActiveJavaFile | undefined> {
  if (!document || document.isUntitled || document.uri.scheme !== 'file' || document.languageId !== 'java') { return; }
  const paths = platform === 'win32' ? path.win32 : path.posix;
  const file = document.uri.fsPath;
  if (!paths.isAbsolute(projectRoot) || !paths.isAbsolute(file) || paths.extname(file).toLowerCase() !== '.java') { return; }
  const relative = paths.relative(projectRoot, file).replace(/\\/g, '/');
  if (!normalizeViolationPath(relative, platform)) { return; }
  try {
    // A lexical child path may still point outside the project through a symlink or junction.
    const [root, target] = await Promise.all([realpath(projectRoot), realpath(file)]);
    if (!normalizeViolationPath(paths.relative(root, target).replace(/\\/g, '/'), platform)) { return; }
    return { filePath: path.posix.normalize(relative), fileName: paths.basename(file) };
  } catch { return undefined; }
}

export function groupViolations(violations: ArchitectureViolation[], activeFile: ActiveJavaFile | undefined,
  platform = process.platform): ViolationGroups {
  const currentFileViolations: ArchitectureViolation[] = [];
  const otherViolations: ArchitectureViolation[] = [];
  const activePath = normalizeViolationPath(activeFile?.filePath, platform);
  for (const violation of violations) {
    const group = activePath && normalizeViolationPath(violation.file_path, platform) === activePath
      ? currentFileViolations : otherViolations;
    group.push(violation);
  }
  return { currentFileViolations, otherViolations };
}
