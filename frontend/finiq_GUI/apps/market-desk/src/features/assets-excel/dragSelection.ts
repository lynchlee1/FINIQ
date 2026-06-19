export function dragSelectionTargetChecked(isSelected: boolean): boolean {
  return !isSelected;
}

export function applyFileSelection(
  current: string[],
  fileName: string,
  checked: boolean,
  canAdd: (current: readonly string[], fileName: string) => boolean = () => true,
): string[] {
  if (checked) {
    if (current.includes(fileName) || !canAdd(current, fileName)) return current;
    return [...current, fileName];
  }
  if (!current.includes(fileName)) return current;
  return current.filter((item) => item !== fileName);
}

export function selectionRowClassName(selected: boolean): string {
  return selected
    ? "bg-sky-50/70 text-slate-900 dark:bg-sky-950/30 dark:text-slate-100"
    : "dark:text-slate-300";
}

export function selectFirstTwoFilesPerAccount(
  fileNames: readonly string[],
  getAccountName: (fileName: string) => string,
): string[] {
  const counts: Record<string, number> = {};
  const selected: string[] = [];
  fileNames.forEach((fileName) => {
    const accountName = getAccountName(fileName);
    const accountCount = counts[accountName] || 0;
    if (accountCount >= 2) return;
    counts[accountName] = accountCount + 1;
    selected.push(fileName);
  });
  return selected;
}

export function formatMergeSelectionSummary(
  selectedFileCount: string,
  mergePairCount: string,
  incompleteAccountNames: readonly string[],
): string {
  const summary = `선택한 파일: ${selectedFileCount}개 / 묶음: ${mergePairCount}개`;
  if (!incompleteAccountNames.length) return summary;
  return `${summary} (1개만 선택된 계정: ${incompleteAccountNames.join(", ")})`;
}
