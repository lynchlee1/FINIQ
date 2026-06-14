"use client"

import { useState, useEffect, useCallback } from "react";
import { Play, Loader2 } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { ActionDock } from "@/components/ui/ActionDock";
import { UI_TEXT } from "@/config/uiText";

interface ProviderField {
  id: string;
  label: string;
  type: "folder" | "file" | "text";
  placeholder?: string;
}

interface Provider {
  id: string;
  name: string;
  fields: ProviderField[];
}

export default function IntegratedDataPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const { integrated_data_values, fetchSettings, saveSetting } = useSettingsStore();
  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus, cancelJob } = useJobPolling({
    pollingEndpoint: "/api/integrated-data/jobs/{jobId}",
    cancelEndpoint: "/api/integrated-data/cancel",
  });


  const fetchProviders = useCallback(async () => {
    try {
      const response = await fetch("/api/integrated-data/providers");
      if (!response.ok) throw new Error("Failed to fetch providers");
      const data = await response.json();
      setProviders(data.providers || []);
      if (data.providers?.length > 0) {
        setSelectedProviderId(data.providers[0].id);
      }
    } catch (err: any) {
      setStatus("Provider 목록을 불러오지 못했습니다: " + err.message);
      setIsErrorStatus(true);
    } finally {
      setLoading(false);
    }
  }, [setStatus, setIsErrorStatus]);

  useEffect(() => {
    fetchProviders();
    fetchSettings();
  }, [fetchProviders, fetchSettings]);

  const handleStartConvert = async () => {
    if (activeJobId) return;
    setStatus("작업을 시작하는 중...");
    setIsErrorStatus(false);

    const payload = {
      provider_id: selectedProviderId,
      ...integrated_data_values,
    };

    try {
      const response = await fetch("/api/integrated-data/convert/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.error || `HTTP ${response.status}`);
      }
      const data = await response.json();
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleFieldChange = (fieldId: string, value: string) => {
    saveSetting("integrated_data_values", {
      ...integrated_data_values,
      [fieldId]: value
    });
  };

  const selectedProvider = providers.find(p => p.id === selectedProviderId);

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  return (
    <WorkflowPageShell workflowId="integrated-data">
      <div className="relative space-y-6">
        <section className="min-w-0 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Source Pipeline</p>
              <CardTitle className="text-xl dark:text-white">원천 데이터 변환</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="providerSelect" className="dark:text-slate-300">데이터 소스 (Source of Truth)</Label>
                <Select value={selectedProviderId} onValueChange={setSelectedProviderId}>
                  <SelectTrigger id="providerSelect" className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                    <SelectValue placeholder="Select a provider" />
                  </SelectTrigger>
                  <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                    {providers.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              {selectedProvider && (
                <div className="grid gap-4 md:grid-cols-2">
                  {selectedProvider.fields.map((field) => (
                    <div key={field.id} className="space-y-2">
                      <Label className="dark:text-slate-300">{field.label}</Label>
                      {(field.type === "folder" || field.type === "file") ? (
                        <PathPickerInput mode={field.type} value={integrated_data_values?.[field.id] || ""} onChange={(val) => handleFieldChange(field.id, val)} placeholder={field.placeholder} onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }} />
                      ) : (
                        <Input placeholder={field.placeholder} value={integrated_data_values?.[field.id] || ""} onChange={(e) => handleFieldChange(field.id, e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                      )}
                    </div>
                  ))}
                </div>
              )}
              <div className="flex gap-2">
                <Button onClick={handleStartConvert} disabled={!!activeJobId} className="w-full md:w-auto">
                  {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                {activeJobId && (
                  <Button variant="outline" onClick={cancelJob} className="w-full md:w-auto">
                    {UI_TEXT.actions.cancelJob}
                  </Button>
                )}
              </div>

            </CardContent>
          </Card>
        </section>
        <ActionDock
          activityActive={!!activeJobId}
          activityContent={
            <JobStatusLogger
              status={status}
              isErrorStatus={isErrorStatus}
              isCancellable={!!activeJobId}
              onCancel={cancelJob}
            />
          }
          notificationActive={isErrorStatus}
          notificationContent={<div className={isErrorStatus ? "whitespace-pre-wrap text-sm text-red-600 dark:text-red-300" : "text-sm text-slate-500 dark:text-slate-400"}>{isErrorStatus ? status : "알림 없음"}</div>}
          settingsTitle="시스템 설정"
          settingsContent={<div className="text-sm text-slate-500 dark:text-slate-400">추가 시스템 설정이 없습니다. 데이터 소스와 입력 필드는 메인 화면에서 조정합니다.</div>}
        />
      </div>
    </WorkflowPageShell>
  );
}
