"use client"

import { useState, useEffect, useCallback } from "react";
import { Play, Loader2, FolderOpen, File } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { WorkflowTabs } from "@/components/layout/WorkflowTabs";
import { cn } from "@finiq/ui/utils";

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

const INTEGRATED_TABS = [
  { href: "/integrated-data", step: 1, label: "원천 데이터 변환" },
  { href: "/integrated-merge", step: 2, label: "Parquet 병합" },
  { href: "/integrated-market-history", step: 3, label: "시장 구분 이력" },
];

export default function IntegratedDataPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState<string>("");
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<string>("종합데이터 구축 작업을 연결할 준비가 되어 있습니다.");
  const [isErrorStatus, setIsErrorStatus] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

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
  }, []);

  useEffect(() => {
    fetchProviders();
  }, [fetchProviders]);

  const pollJob = useCallback(async (jobId: string) => {
    try {
      const response = await fetch(`/api/disclosures/html/jobs/${encodeURIComponent(jobId)}`);
      if (!response.ok) throw new Error("Job polling failed");
      const data = await response.json();
      
      const statusLabel = (s: string) => {
        switch(s) {
          case "queued": return "대기 중";
          case "running": return "실행 중";
          case "completed": return "완료";
          case "failed": return "실패";
          default: return s || "-";
        }
      };

      const lines = [`작업 상태: ${statusLabel(data.status)}`];
      if (data.error) lines.push(`오류: ${data.error}`);
      if (data.progress_log?.length) {
        lines.push("", "최근 로그:", ...data.progress_log.slice(-10));
      }
      
      setStatus(lines.join("\n"));
      setIsErrorStatus(data.status === "failed");

      if (data.status === "completed" || data.status === "failed") {
        setActiveJobId(null);
        return;
      }
      
      setTimeout(() => pollJob(jobId), 1000);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
      setActiveJobId(null);
    }
  }, []);

  const handleStartConvert = async () => {
    if (activeJobId) return;
    setStatus("작업을 시작하는 중...");
    setIsErrorStatus(false);

    const payload = {
      provider_id: selectedProviderId,
      ...fieldValues,
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
      setActiveJobId(data.job_id);
      pollJob(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handlePickPath = async (fieldId: string, mode: "folder" | "file", label: string) => {
    try {
      const response = await fetch("/api/file-dialog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          mode: mode === "folder" ? "dir" : "file", 
          title: `${label} 선택`, 
          default_path: fieldValues[fieldId] || "" 
        }),
      });
      const data = await response.json();
      if (data.path) {
        setFieldValues(prev => ({ ...prev, [fieldId]: data.path }));
      }
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const selectedProvider = providers.find(p => p.id === selectedProviderId);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
        <p className="text-slate-500 font-medium">Provider 정보를 불러오는 중입니다...</p>
      </div>
    );
  }

  return (
    <main className="flex flex-col w-full">
      <WorkflowTabs tabs={INTEGRATED_TABS} />

      <div className="space-y-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Source Pipeline</p>
              <CardTitle className="text-xl">원천 데이터 변환</CardTitle>
            </div>
            <Button 
              onClick={handleStartConvert} 
              disabled={!!activeJobId}
              className="bg-slate-900 text-white hover:bg-slate-800"
            >
              {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              변환 시작
            </Button>
          </CardHeader>
          <CardContent className="pt-6 space-y-6">
            <div className="space-y-2">
              <Label htmlFor="providerSelect">데이터 소스 (Source of Truth)</Label>
              <Select value={selectedProviderId} onValueChange={setSelectedProviderId}>
                <SelectTrigger id="providerSelect">
                  <SelectValue placeholder="Select a provider" />
                </SelectTrigger>
                <SelectContent>
                  {providers.map(p => (
                    <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {selectedProvider && (
              <div className="grid md:grid-cols-2 gap-4">
                {selectedProvider.fields.map((field) => (
                  <div key={field.id} className="space-y-2">
                    <Label htmlFor={`field_${field.id}`}>{field.label}</Label>
                    <div className="flex gap-2">
                      <Input 
                        id={`field_${field.id}`}
                        placeholder={field.placeholder}
                        value={fieldValues[field.id] || ""}
                        onChange={(e) => setFieldValues(prev => ({ ...prev, [field.id]: e.target.value }))}
                      />
                      {(field.type === "folder" || field.type === "file") && (
                        <Button 
                          variant="outline" 
                          size="icon" 
                          onClick={() => handlePickPath(field.id, field.type as "folder" | "file", field.label)}
                        >
                          {field.type === "folder" ? <FolderOpen className="h-4 w-4" /> : <File className="h-4 w-4" />}
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Validation</p>
            <CardTitle className="text-xl">검증 결과</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={cn(
              "p-4 rounded-lg border font-mono text-xs whitespace-pre-wrap min-h-[120px]",
              isErrorStatus ? "bg-red-50 border-red-200 text-red-700" : "bg-slate-50 border-slate-200 text-slate-700"
            )}>
              {status}
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
