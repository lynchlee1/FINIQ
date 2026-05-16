"use client"

import { useState, useEffect, useCallback } from "react";
import { FolderOpen, Play, RefreshCw, Loader2 } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { WorkflowTabs } from "@/components/layout/WorkflowTabs";
import { cn } from "@finiq/ui/utils";

const BUILD_TABS = [
  { href: "/download", step: 1, label: "공시 다운로드" },
  { href: "/table", step: 2, label: "SQLITE 변환" },
  { href: "/filter", step: 3, label: "공시 필터" },
];

export default function TablePage() {
  const [loading, setLoading] = useState(true);
  const [isBuilding, setIsBuilding] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [isErrorStatus, setIsErrorStatus] = useState(false);
  
  // Data State
  const [classificationOptions, setClassificationOptions] = useState<any[]>([]);

  // Form State
  const [classificationPath, setClassificationPath] = useState("");
  const [outputPath, setOutputPath] = useState("");

  const outputDirectoryFromRawPath = (path: string) => {
    const normalized = String(path || "").trim();
    if (!normalized) return "";
    if (/\.json$/i.test(normalized)) return normalized.replace(/\.json$/i, "_sqlite");
    return normalized.replace(/\/?$/, "/kind_sqlite");
  };

  const outputDirectoryFromSavedPath = (path: string) => {
    const normalized = String(path || "").trim();
    if (!/\.sqlite_manifest\.json$/i.test(normalized)) return normalized;
    return normalized.replace(/\/[^/]*$/i, "");
  };

  const loadClassifications = useCallback(async (rootDirectory: string, selectedPath: string = "", selectedOutputPath: string = "") => {
    try {
      const url = new URL("/api/classifications", window.location.origin);
      url.searchParams.set("root_directory", rootDirectory);
      const response = await fetch(url.pathname + url.search);
      if (!response.ok) throw new Error("Failed to load classifications");
      const data = await response.json();
      
      const files = data.classification_files || [];
      setClassificationOptions(files);
      
      const path = selectedPath || data.selected_classification_path || (files.length > 0 ? files[0].path : "");
      setClassificationPath(path);
      
      const outPath = outputDirectoryFromSavedPath(selectedOutputPath) || outputDirectoryFromRawPath(path);
      setOutputPath(outPath);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  }, []);

  const fetchConfig = useCallback(async () => {
    try {
      const response = await fetch("/api/config");
      if (!response.ok) throw new Error("Failed to fetch config");
      const config = await response.json();
      
      await loadClassifications(
        config.output_root || "",
        config.sqlite_source_path || config.selected_classification_path || "",
        config.sqlite_manifest_path || ""
      );
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setLoading(false);
    }
  }, [loadClassifications]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleClassificationPathChange = (val: string) => {
    setClassificationPath(val);
    setOutputPath(outputDirectoryFromRawPath(val));
  };

  const saveSetting = async (key: string, value: string) => {
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: value }),
      });
    } catch (err) {
      console.error(`Failed to save setting ${key}:`, err);
    }
  };

  const handlePickPath = async (type: 'dir' | 'file', setter: (v: string) => void, defaultPath: string) => {
    try {
      const response = await fetch("/api/file-dialog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: type, title: "선택", default_path: defaultPath }),
      });
      const data = await response.json();
      if (data.path) {
        if (setter === setClassificationPath) {
          handleClassificationPathChange(data.path);
          saveSetting("sqlite_source_path", data.path);
        } else {
          setter(data.path);
          if (setter === setOutputPath) {
            saveSetting("output_root", data.path);
          }
        }
      }
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleRefresh = async () => {
    try {
      setStatus("소스를 새로고침하는 중...");
      const response = await fetch("/api/config");
      const config = await response.json();
      await loadClassifications(config.output_root || "", classificationPath);
      setStatus("소스를 새로고침했습니다.");
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleBuild = async () => {
    if (!classificationPath) {
      setStatus("Raw JSON을 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    
    setIsBuilding(true);
    setStatus("SQLite 테이블 생성 중...");
    setIsErrorStatus(false);

    try {
      const response = await fetch("/api/disclosures/table/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          classification_path: classificationPath,
          output_path: outputPath,
          table_name: "disclosures",
        }),
      });
      
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.error || "Build failed");
      }
      
      const data = await response.json();
      const summary = data.summary || {};
      setStatus(`연도별 SQLite shard를 저장했습니다: ${outputPath || data.output_path}\n회사: ${summary.companies || 0} · 공시: ${summary.disclosures || 0} · Shard: ${summary.shards || 0} · FTS: ${summary.fts_enabled ? "ON" : "OFF"}`);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setIsBuilding(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
        <p className="text-slate-500 font-medium">설정을 불러오는 중입니다...</p>
      </div>
    );
  }

  return (
    <main className="flex flex-col gap-6 w-full">
      <WorkflowTabs tabs={BUILD_TABS} />
      
      <Card>
        <CardHeader>
          <CardTitle>SQLITE 변환</CardTitle>
          <CardDescription>회사별로 분류된 Raw JSON 데이터를 검색과 분석에 용이한 SQLite 형식으로 변환합니다.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label>입력 경로 (Raw JSON 폴더)</Label>
              <div className="flex gap-2">
                <Input
                  value={classificationPath}
                  onChange={(e) => handleClassificationPathChange(e.target.value)}
                  onBlur={() => saveSetting("sqlite_source_path", classificationPath)}
                  list="classificationPathOptions"
                />

                <datalist id="classificationPathOptions">
                  {classificationOptions.map(opt => (
                    <option key={opt.path} value={opt.path}>{opt.label || opt.name}</option>
                  ))}
                </datalist>
                <Button variant="outline" size="icon" onClick={() => handlePickPath('dir', setClassificationPath, classificationPath)}>
                  <FolderOpen className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label>저장 경로 (SQLite)</Label>
              <div className="flex gap-2">
                <Input 
                  value={outputPath} 
                  onChange={(e) => setOutputPath(e.target.value)} 
                  onBlur={() => saveSetting("output_root", outputPath)}
                />
                <Button variant="outline" size="icon" onClick={() => handlePickPath('dir', setOutputPath, outputPath)}>
                  <FolderOpen className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>

          <div className="flex gap-3">
            <Button variant="outline" onClick={handleRefresh} disabled={isBuilding}>
              <RefreshCw className={cn("mr-2 h-4 w-4", isBuilding ? "animate-spin" : "")} />
              소스 새로고침
            </Button>
            <Button className="flex-1" onClick={handleBuild} disabled={isBuilding}>
              {isBuilding ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              테이블 생성
            </Button>
          </div>

          <div className="space-y-2">
            <Label>진행 상태</Label>
            <div className={cn(
              "p-4 rounded-lg border min-h-[100px] whitespace-pre-wrap font-mono text-xs",
              isErrorStatus ? "bg-red-50 border-red-200 text-red-700" : "bg-slate-50 border-slate-200 text-slate-700"
            )}>
              {status || "대기 중..."}
            </div>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
