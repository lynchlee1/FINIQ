"use client";

import { useEffect, useState } from "react";
import { Button } from "@finiq/ui";
import { apiPost } from "@/api/client";
import { PathPickerInput } from "@/components/ui/PathPickerInput";

export const DISCLOSURE_STORAGE_STAGES = [
  { name: "01-list", label: "01 공시내역 다운로드" },
  { name: "02-table", label: "02 공시내역 변환" },
  { name: "03-filter", label: "03 공시내역 필터링" },
  { name: "04-external-html-download", label: "04 외부 HTML 저장" },
  { name: "04-external-html-compress", label: "04 외부 HTML 압축" },
  { name: "05-internal-html-download", label: "05 공시원문 내부 저장" },
  { name: "06-sections", label: "06 공시원문 목차 분리" },
  { name: "07-converted", label: "07 공시원문 변환" },
] as const;

export type DisclosureStorageStage = (typeof DISCLOSURE_STORAGE_STAGES)[number]["name"];

type StageLinkStatus = {
  stage: DisclosureStorageStage;
  linked: boolean;
  valid: boolean;
  local_directory: string;
  target_workspace: string | null;
  resolved_directory: string;
  error: string | null;
};

type StageLinksResponse = {
  data_root: string;
  stages: StageLinkStatus[];
};

type DisclosureStageStorageSettingsProps = {
  dataRoot: string;
  stages?: DisclosureStorageStage[];
  disabled?: boolean;
  onChanged?: () => void;
  onError: (message: string) => void;
};

const endpoint = "/api/disclosures/workspace/stage-links";

export function DisclosureStageStorageSettings({
  dataRoot,
  stages,
  disabled = false,
  onChanged,
  onError,
}: DisclosureStageStorageSettingsProps) {
  const [result, setResult] = useState<StageLinksResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [editingStage, setEditingStage] = useState<DisclosureStorageStage | null>(null);
  const [targetWorkspace, setTargetWorkspace] = useState("");
  const [busyStage, setBusyStage] = useState<DisclosureStorageStage | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const root = dataRoot.trim();
    setEditingStage(null);
    setTargetWorkspace("");
    setMessage("");
    if (!root) {
      setResult(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    apiPost<StageLinksResponse>(endpoint, { data_root: root, action: "list" }, { signal: controller.signal })
      .then(setResult)
      .catch((error) => {
        if (controller.signal.aborted) return;
        const errorMessage = error instanceof Error ? error.message : "단계별 저장 위치를 불러오지 못했습니다.";
        setResult(null);
        setMessage(errorMessage);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [dataRoot]);

  const visibleStages = DISCLOSURE_STORAGE_STAGES.filter(
    (stage) => !stages || stages.includes(stage.name),
  );

  const startEditing = (status: StageLinkStatus) => {
    setEditingStage(status.stage);
    setTargetWorkspace(status.target_workspace || "");
    setMessage("");
  };

  const saveLink = async (stage: DisclosureStorageStage) => {
    if (!targetWorkspace.trim()) {
      setMessage("대상 작업공간을 선택하세요.");
      return;
    }
    setBusyStage(stage);
    setMessage("");
    try {
      const next = await apiPost<StageLinksResponse>(endpoint, {
        data_root: dataRoot.trim(),
        action: "set",
        stage,
        target_workspace: targetWorkspace.trim(),
      });
      setResult(next);
      setEditingStage(null);
      setTargetWorkspace("");
      setMessage("단계별 저장 위치를 저장했습니다.");
      onChanged?.();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "단계별 저장 위치를 저장하지 못했습니다.";
      setMessage(errorMessage);
      onError(errorMessage);
    } finally {
      setBusyStage(null);
    }
  };

  const removeLink = async (stage: DisclosureStorageStage) => {
    setBusyStage(stage);
    setMessage("");
    try {
      const next = await apiPost<StageLinksResponse>(endpoint, {
        data_root: dataRoot.trim(),
        action: "remove",
        stage,
      });
      setResult(next);
      setEditingStage(null);
      setTargetWorkspace("");
      setMessage("단계 연결을 해제했습니다. 저장된 데이터는 삭제되지 않았습니다.");
      onChanged?.();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "단계 연결을 해제하지 못했습니다.";
      setMessage(errorMessage);
      onError(errorMessage);
    } finally {
      setBusyStage(null);
    }
  };

  return (
    <section className="space-y-2.5" aria-labelledby="disclosure-stage-storage-title">
      <div className="border-b border-[color:var(--tv-border)] pb-2">
        <p id="disclosure-stage-storage-title" className="text-caption font-semibold tracking-wide text-slate-500 dark:text-slate-400">
          단계별 저장 위치
        </p>
      </div>
      {!dataRoot.trim() ? (
        <p className="text-caption text-[var(--tv-muted)]">작업공간 디렉토리를 먼저 선택하세요.</p>
      ) : loading ? (
        <p className="text-caption text-[var(--tv-muted)]">저장 위치를 불러오는 중입니다.</p>
      ) : !result ? (
        <p className="text-caption text-[var(--tv-muted)]">저장 위치를 불러오지 못했습니다.</p>
      ) : (
        <div className="divide-y divide-[color:var(--tv-border)]">
          {visibleStages.map((stage) => {
            const status = result.stages.find((item) => item.stage === stage.name);
            if (!status) return null;
            const isEditing = editingStage === stage.name;
            const isBusy = busyStage === stage.name;
            return (
              <div key={stage.name} className="space-y-2 py-2.5 first:pt-0 last:pb-0">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-body font-medium text-[var(--tv-text)]">{stage.label}</p>
                    <p className="mt-0.5 break-all font-mono text-caption text-[var(--tv-muted)]">
                      {status.linked && status.valid ? status.resolved_directory : status.linked ? "설정 오류" : "로컬"}
                    </p>
                    {status.error ? (
                      <p className="mt-1 break-all text-caption text-red-700 dark:text-red-400">
                        {status.error}
                      </p>
                    ) : null}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-8 shrink-0"
                    disabled={disabled || busyStage !== null}
                    onClick={() => startEditing(status)}
                  >
                    {status.linked ? "변경" : "연결"}
                  </Button>
                </div>
                {isEditing ? (
                  <div className="space-y-2 rounded-md bg-[var(--tv-control)] p-2.5">
                    <p className="text-caption font-medium text-[var(--tv-text)]">대상 작업공간</p>
                    <PathPickerInput
                      mode="folder"
                      value={targetWorkspace}
                      onChange={setTargetWorkspace}
                      title="대상 작업공간 선택"
                      placeholder="작업공간 루트를 선택하세요"
                      disabled={disabled || isBusy}
                      onError={(error) => onError(error.message)}
                    />
                    {targetWorkspace.trim() ? (
                      <p className="break-all font-mono text-caption text-[var(--tv-muted)]">
                        저장 위치: {targetWorkspace.replace(/\/$/, "")}/{stage.name}
                      </p>
                    ) : null}
                    <div className="flex flex-wrap justify-end gap-2">
                      {status.linked ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={disabled || isBusy}
                          onClick={() => void removeLink(stage.name)}
                        >
                          연결 해제
                        </Button>
                      ) : null}
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={isBusy}
                        onClick={() => {
                          setEditingStage(null);
                          setTargetWorkspace("");
                        }}
                      >
                        취소
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        disabled={disabled || isBusy || !targetWorkspace.trim()}
                        onClick={() => void saveLink(stage.name)}
                      >
                        {isBusy ? "저장 중" : "변경사항 저장"}
                      </Button>
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
      {message ? <p role="status" className="text-caption text-[var(--tv-muted)]">{message}</p> : null}
    </section>
  );
}
