export function canCheckConformance(prerequisitesReady: boolean, ...operationsRunning: boolean[]): boolean {
  // Only analysis, context sync and conformance belong here; rule generation is independent.
  return prerequisitesReady && !operationsRunning.some(running => running);
}
