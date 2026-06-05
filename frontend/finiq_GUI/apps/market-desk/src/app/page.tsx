"use client"

import { useState, useEffect, useCallback } from "react";
import { Settings, FolderOpen, Search, Building2, Calendar, FileText } from "lucide-react";
import { Input } from "@finiq/ui";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@finiq/ui";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { cn } from "@finiq/ui/utils";
import { pickPath, type PathDialogMode } from "@/lib/fileDialog";

interface ConfigFile {
  path: string;
  label: string;
}

interface Config {
  output_root: string;
  quanti_dir: string;
  price_root_directory: string;
  selected_price_path: string;
  selected_classification_path: string;
  price_files: ConfigFile[];
  classification_files: ConfigFile[];
  range_options: string[];
  display_frequency_options: string[];
}

interface Company {
  company_key: string;
  company_name: string;
  market: string;
  badges: string[];
  last_disclosed_at: string;
  disclosure_count: number;
}

export default function Home() {
  const router = useRouter();
  const [settingsOpen, setSettingsOpen] = useState(true);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [outputRoot, setOutputRoot] = useState("");
  const [priceRootDir, setPriceRootDir] = useState("");
  const [selectedPricePath, setSelectedPricePath] = useState("");
  const [selectedClassificationPath, setSelectedClassificationPath] = useState("");
  const [priceFiles, setPriceFiles] = useState<ConfigFile[]>([]);
  const [classificationFiles, setClassificationFiles] = useState<ConfigFile[]>([]);

  const [displayCount, setDisplayCount] = useState(100);

  const fetchConfig = useCallback(async () => {
    try {
      const response = await fetch("/api/config");
      if (!response.ok) throw new Error("Failed to fetch config");
      const data: Config = await response.json();
      setOutputRoot(data.output_root);
      setPriceRootDir(data.price_root_directory);
      setSelectedPricePath(data.selected_price_path || data.quanti_dir);
      setSelectedClassificationPath(data.selected_classification_path);
    } catch (err: any) {
      setError(err.message);
    }
  }, []);

  const fetchCompanies = useCallback(async (path: string, kw: string) => {
    if (!path) return;
    try {
      setLoading(true);
      const params = new URLSearchParams({
        classification_path: path,
        keyword: kw,
      });
      const response = await fetch(`/api/companies?${params.toString()}`);
      if (!response.ok) throw new Error("Failed to fetch companies");
      const data = await response.json();
      setCompanies(data.companies || []);
      setDisplayCount(100); // Reset display count on new search
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchPriceFiles = useCallback(async (rootDirectory: string, selectedPath: string) => {
    if (!rootDirectory) return;
    try {
      const params = new URLSearchParams({ root_directory: rootDirectory });
      if (selectedPath) params.set("selected_path", selectedPath);
      const response = await fetch(`/api/price-sources?${params.toString()}`);
      if (!response.ok) throw new Error("Failed to fetch price sources");
      const data = await response.json();
      setPriceFiles(data.price_files || []);
      if (data.selected_price_path) setSelectedPricePath(data.selected_price_path);
    } catch (err: any) {
      setError(err.message);
    }
  }, []);

  const fetchClassificationFiles = useCallback(async (rootDirectory: string) => {
    if (!rootDirectory) return;
    try {
      const params = new URLSearchParams({ root_directory: rootDirectory });
      const response = await fetch(`/api/classifications?${params.toString()}`);
      if (!response.ok) throw new Error("Failed to fetch classifications");
      const data = await response.json();
      setClassificationFiles(data.classification_files || []);
      if (!selectedClassificationPath && data.selected_classification_path) {
        setSelectedClassificationPath(data.selected_classification_path);
      }
    } catch (err: any) {
      setError(err.message);
    }
  }, [selectedClassificationPath]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  useEffect(() => {
    if (!selectedClassificationPath) return;

    if (!keyword) {
      fetchCompanies(selectedClassificationPath, "");
      return;
    }

    const timer = setTimeout(() => {
      fetchCompanies(selectedClassificationPath, keyword);
    }, 300);
    return () => clearTimeout(timer);
  }, [selectedClassificationPath, keyword, fetchCompanies]);

  const handlePickPath = async (mode: PathDialogMode, setter: (path: string) => void, defaultPath: string) => {
    try {
      const path = await pickPath({ mode, title: "경로 선택", defaultPath });
      if (path) {
        setter(path);
        // If we picked a directory for price or output, we might want to reload files
        if (mode === 'folder') {
          await handleSaveSettings(path, setter === setOutputRoot ? 'output' : 'price');
        } else if (setter === setSelectedClassificationPath) {
          await handleSaveSettings(path, 'classification');
        }
      }
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleSaveSettings = async (pathOverride?: string, type?: 'output' | 'price' | 'priceFile' | 'classification') => {
    try {
      const payload = {
        output_root: type === 'output' ? pathOverride : outputRoot,
        selected_classification_path: type === 'classification' ? pathOverride : selectedClassificationPath,
        price_root_directory: type === 'price' ? pathOverride : priceRootDir,
        quanti_dir: type === 'priceFile' ? pathOverride : selectedPricePath,
      };
      
      const response = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("Failed to save settings");
      const data: Config = await response.json();
      if (!pathOverride) {
        setOutputRoot(data.output_root);
        setPriceRootDir(data.price_root_directory);
        setSelectedPricePath(data.selected_price_path || data.quanti_dir);
        setSelectedClassificationPath(data.selected_classification_path);
      }
    } catch (err: any) {
      setError(err.message);
    }
  };

  const formatNumber = (val: number) => new Intl.NumberFormat("ko-KR").format(val);
  const visiblePriceFiles = selectedPricePath && !priceFiles.some((file) => file.path === selectedPricePath)
    ? [{ path: selectedPricePath, label: selectedPricePath }, ...priceFiles]
    : priceFiles;
  const visibleClassificationFiles = selectedClassificationPath && !classificationFiles.some((file) => file.path === selectedClassificationPath)
    ? [{ path: selectedClassificationPath, label: selectedClassificationPath }, ...classificationFiles]
    : classificationFiles;

  return (
    <main className="flex flex-col gap-6 w-full">
      <section className="flex items-center gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input 
            type="search" 
            placeholder="회사명을 입력하세요." 
            className="pl-10 h-12 bg-white dark:bg-[#161b22] dark:border-[#30363d] dark:text-white"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>
        <Button 
          variant="outline" 
          size="lg"
          onClick={() => setSettingsOpen(!settingsOpen)}
          className={cn(settingsOpen ? "bg-slate-100 dark:bg-[#21262d]" : "", "dark:border-[#30363d] dark:text-slate-300 dark:hover:bg-[#21262d]")}
        >
          <Settings className="mr-2 h-4 w-4" />
          설정
        </Button>
      </section>

      {settingsOpen && (
        <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
          <CardContent className="p-6">
            <div className="grid md:grid-cols-2 gap-8">
              <div className="space-y-4">
                <h3 className="font-semibold text-slate-900 dark:text-white border-b dark:border-[#30363d] pb-2">주가 소스</h3>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">폴더 경로</Label>
                  <div className="flex gap-2">
                    <Input 
                      placeholder="/path/to/price/folder" 
                      value={priceRootDir} 
                      onChange={(e) => {
                        setPriceRootDir(e.target.value);
                        setPriceFiles([]);
                      }}
                      onBlur={() => handleSaveSettings(priceRootDir, 'price')}
                      className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                    />
                    <Button 
                      variant="outline" 
                      size="icon" 
                      title="폴더 선택"
                      onClick={() => handlePickPath('folder', setPriceRootDir, priceRootDir)}
                      className="dark:border-[#30363d] dark:hover:bg-[#21262d]"
                    >
                      <FolderOpen className="h-4 w-4 dark:text-slate-400" />
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">파일 선택</Label>
                  <Select 
                    value={selectedPricePath} 
                    onOpenChange={(open) => {
                      if (open && priceFiles.length === 0) {
                        fetchPriceFiles(priceRootDir, selectedPricePath);
                      }
                    }}
                    onValueChange={(val) => {
                      setSelectedPricePath(val);
                      handleSaveSettings(val, 'priceFile');
                    }}
                  >
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                      <SelectValue placeholder="파일을 선택하세요" />
                    </SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      {visiblePriceFiles.map((file) => (
                        <SelectItem key={file.path} value={file.path}>
                          {file.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-4">
                <h3 className="font-semibold text-slate-900 dark:text-white border-b dark:border-[#30363d] pb-2">공시 소스</h3>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">폴더 경로</Label>
                  <div className="flex gap-2">
                    <Input 
                      placeholder="/path/to/disclosure/folder" 
                      value={outputRoot}
                      onChange={(e) => {
                        setOutputRoot(e.target.value);
                        setClassificationFiles([]);
                      }}
                      onBlur={() => handleSaveSettings(outputRoot, 'output')}
                      className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                    />
                    <Button 
                      variant="outline" 
                      size="icon" 
                      title="폴더 선택"
                      onClick={() => handlePickPath('folder', setOutputRoot, outputRoot)}
                      className="dark:border-[#30363d] dark:hover:bg-[#21262d]"
                    >
                      <FolderOpen className="h-4 w-4 dark:text-slate-400" />
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">파일 선택</Label>
                  <Select 
                    value={selectedClassificationPath} 
                    onOpenChange={(open) => {
                      if (open && classificationFiles.length === 0) {
                        fetchClassificationFiles(outputRoot);
                      }
                    }}
                    onValueChange={(val) => {
                      setSelectedClassificationPath(val);
                      handleSaveSettings(val, 'classification');
                    }}
                  >
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                      <SelectValue placeholder="파일을 선택하세요" />
                    </SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      {visibleClassificationFiles.map((file) => (
                        <SelectItem key={file.path} value={file.path}>
                          {file.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
            <div className="mt-8 flex justify-end">
              <Button onClick={() => handleSaveSettings()}>설정 저장</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <div>
            <CardDescription className="dark:text-slate-400">회사 목록</CardDescription>
            <CardTitle className="dark:text-white">회사 코드</CardTitle>
          </div>
          <div className="bg-slate-100 dark:bg-[#21262d] text-slate-700 dark:text-slate-200 px-3 py-1 rounded-full text-sm font-semibold">
            {formatNumber(companies.length)}
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-12 text-slate-500 dark:text-slate-400">
              데이터를 불러오는 중입니다...
            </div>
          ) : companies.length > 0 ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {companies.slice(0, displayCount).map((company) => {
                  const params = new URLSearchParams({
                    classification_path: selectedClassificationPath,
                    root_directory: outputRoot,
                    price_root_directory: priceRootDir,
                    price_dir: selectedPricePath,
                  });
                  const href = `/company/${company.company_key}?${params.toString()}`;

                  return (
                    <Link
                      key={company.company_key}
                      href={href}
                      className="flex flex-col p-4 rounded-xl border border-slate-200 dark:border-[#30363d] hover:border-slate-900 dark:hover:border-slate-100 hover:shadow-md transition-all text-left bg-white dark:bg-[#0d1117]/50 group"
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex flex-col">
                          <span className="text-xs font-bold text-slate-400 dark:text-slate-500 mb-1">{company.company_key}</span>
                          <h4 className="font-bold text-slate-900 dark:text-slate-200 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                            {company.company_name}
                          </h4>
                        </div>
                        <span className="px-2 py-1 rounded bg-slate-100 dark:bg-[#21262d] text-[10px] font-bold text-slate-600 dark:text-slate-400">
                          {company.market}
                        </span>
                      </div>
                      
                      <div className="flex flex-wrap gap-1 mb-4">
                        {company.badges?.slice(0, 3).map((tag, i) => (
                          <span key={i} className="px-1.5 py-0.5 rounded-md bg-blue-50 dark:bg-blue-900/20 text-[10px] font-medium text-blue-600 dark:text-blue-400 border border-blue-100 dark:border-blue-900/50">
                            {tag}
                          </span>
                        ))}
                      </div>

                      <div className="mt-auto grid grid-cols-2 gap-2 pt-3 border-t border-slate-50 dark:border-[#30363d]">
                        <div className="flex flex-col">
                          <span className="text-[10px] text-slate-400 dark:text-slate-500">최근 공시</span>
                          <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">{company.last_disclosed_at || "-"}</span>
                        </div>
                        <div className="flex flex-col">
                          <span className="text-[10px] text-slate-400 dark:text-slate-500">공시 건수</span>
                          <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">{formatNumber(company.disclosure_count)}건</span>
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
              {companies.length > displayCount && (
                <div className="mt-8 flex justify-center">
                  <Button variant="outline" onClick={() => setDisplayCount(prev => prev + 100)} className="dark:border-[#30363d] dark:text-slate-300 dark:hover:bg-[#21262d]">
                    더 보기 ({formatNumber(companies.length - displayCount)}개 남음)
                  </Button>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-12 text-slate-500 dark:text-slate-400">
              {error ? `오류: ${error}` : "조건에 맞는 회사가 없습니다."}
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
