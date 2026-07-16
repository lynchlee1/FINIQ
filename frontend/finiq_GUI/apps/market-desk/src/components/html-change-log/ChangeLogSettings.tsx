import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Button, Input, Label } from "@finiq/ui";
import { useSettingsStore } from "@/store/useSettingsStore";

export const DATE_FIELDS_CONFIG = [
  { field: "만기일", default: 3 },
  { field: "행사시작일", default: 3 },
  { field: "행사종료일", default: 3 },
  { field: "납입일", default: 3 },
  { field: "신주권교부예정일", default: 3 },
  { field: "상장예정일", default: 3 },
  { field: "기준일", default: 3 },
  { field: "권리배정기준일", default: 3 },
];

export const NUMERIC_FIELDS_CONFIG = [
  { field: "발행금액", default: 1 },
  { field: "발행가액", default: 1 },
  { field: "행사가액", default: 1 },
  { field: "신주의 종류와 수", default: 1 },
];

export function ChangeLogSettings() {
  const { change_log_date_thresholds, change_log_numeric_thresholds, saveSetting } = useSettingsStore();
  const [showDetails, setShowDetails] = useState(false);

  const dateThresholds = change_log_date_thresholds || {};
  const numericThresholds = change_log_numeric_thresholds || {};

  const handleDateChange = (field: string, val: number) => {
    saveSetting("change_log_date_thresholds", { ...dateThresholds, [field]: val });
  };

  const handleNumericChange = (field: string, val: number) => {
    saveSetting("change_log_numeric_thresholds", { ...numericThresholds, [field]: val });
  };

  const handleBulkDateChange = (val: number) => {
    saveSetting("change_log_date_thresholds", Object.fromEntries(DATE_FIELDS_CONFIG.map((c) => [c.field, val])));
  };

  const handleBulkNumericChange = (val: number) => {
    saveSetting("change_log_numeric_thresholds", Object.fromEntries(NUMERIC_FIELDS_CONFIG.map((c) => [c.field, val])));
  };

  const handleReset = () => {
    saveSetting("change_log_date_thresholds", Object.fromEntries(DATE_FIELDS_CONFIG.map((c) => [c.field, c.default])));
    saveSetting("change_log_numeric_thresholds", Object.fromEntries(NUMERIC_FIELDS_CONFIG.map((c) => [c.field, c.default])));
  };

  return (
    <div className="space-y-5">
      <div className="space-y-3 border-b border-slate-200 pb-3 dark:border-[#30363d]">
        <h4 className="text-sm font-bold text-slate-900 dark:text-slate-200">변동 임계값</h4>
        <div className="flex flex-wrap items-center gap-2">
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => setShowDetails(!showDetails)}
            className="h-8 text-[10px] font-bold text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 flex items-center gap-1"
          >
            {showDetails ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            세부 설정 {showDetails ? "접기" : "펼치기"}
          </Button>
          <Button variant="outline" size="sm" onClick={handleReset} className="h-8 text-[10px] font-bold dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-300">초기화</Button>
        </div>
      </div>
      
      <div className="space-y-6 py-2">
        {/* Date Fields Column */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-slate-500" />
              <h5 className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">날짜 필드 (일수 차이)</h5>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-[11px] text-slate-400 dark:text-slate-500 font-bold">일괄 조절</Label>
              <div className="flex items-center gap-1 bg-white dark:bg-[#0d1117] border border-slate-200 dark:border-[#30363d] rounded px-1.5 py-0.5">
                <Input 
                  type="number" 
                  min="0" 
                  max="30" 
                  className="w-10 h-5 border-none bg-transparent text-[11px] focus-visible:ring-0 p-0 text-center font-bold dark:text-slate-300"
                  onChange={(e) => handleBulkDateChange(Number(e.target.value))}
                  placeholder="0"
                />
                <span className="text-[11px] text-slate-400 dark:text-slate-500 font-bold">일</span>
              </div>
            </div>
          </div>
          
          {showDetails && (
            <div className="grid grid-cols-1 gap-1.5 animate-in fade-in slide-in-from-top-1">
              {DATE_FIELDS_CONFIG.map(({ field, default: def }) => (
                <div key={field} className="space-y-1.5 p-2 rounded-lg bg-slate-50/50 dark:bg-[#0d1117]/30 border border-slate-100 dark:border-[#30363d]">
                  <div className="flex items-center justify-between">
                    <Label className="text-[11px] font-bold text-slate-600 dark:text-slate-300">{field}</Label>
                    <div className="flex items-center gap-1 bg-slate-100 dark:bg-[#21262d] px-1.5 py-0.5 rounded border border-transparent focus-within:border-slate-300 dark:focus-within:border-[#484f58] transition-colors">
                      <Input 
                        type="number"
                        min="0"
                        max="30"
                        value={dateThresholds[field] ?? def}
                        onChange={(e) => handleDateChange(field, Number(e.target.value))}
                        className="w-8 h-4 border-none bg-transparent text-[11px] font-bold focus-visible:ring-0 p-0 text-center dark:text-slate-200"
                      />
                      <span className="text-[11px] text-slate-400 dark:text-slate-500 font-bold">일</span>
                    </div>
                  </div>
                  <Input 
                    type="range" 
                    min="0" 
                    max="30" 
                    step="1" 
                    value={dateThresholds[field] ?? def} 
                    onChange={(e) => handleDateChange(field, Number(e.target.value))}
                    className="h-4 accent-slate-600 dark:accent-slate-400 cursor-pointer"
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Numeric Fields Column */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-slate-500" />
              <h5 className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">수치 필드 (변동폭 %)</h5>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-[11px] text-slate-400 dark:text-slate-500 font-bold">일괄 조절</Label>
              <div className="flex items-center gap-1 bg-white dark:bg-[#0d1117] border border-slate-200 dark:border-[#30363d] rounded px-1.5 py-0.5">
                <Input 
                  type="number" 
                  min="0" 
                  max="100" 
                  step="0.5"
                  className="w-10 h-5 border-none bg-transparent text-[11px] focus-visible:ring-0 p-0 text-center font-bold dark:text-slate-300"
                  onChange={(e) => handleBulkNumericChange(Number(e.target.value))}
                  placeholder="0.0"
                />
                <span className="text-[11px] text-slate-400 dark:text-slate-500 font-bold">%</span>
              </div>
            </div>
          </div>

          {showDetails && (
            <div className="grid grid-cols-1 gap-1.5 animate-in fade-in slide-in-from-top-1">
              {NUMERIC_FIELDS_CONFIG.map(({ field, default: def }) => (
                <div key={field} className="space-y-1.5 p-2 rounded-lg bg-slate-50/50 dark:bg-[#0d1117]/30 border border-slate-100 dark:border-[#30363d]">
                  <div className="flex items-center justify-between">
                    <Label className="text-[11px] font-bold text-slate-600 dark:text-slate-300">{field}</Label>
                    <div className="flex items-center gap-1 bg-slate-100 dark:bg-[#21262d] px-1.5 py-0.5 rounded border border-transparent focus-within:border-slate-300 dark:focus-within:border-[#484f58] transition-colors">
                      <Input 
                        type="number"
                        min="0"
                        max="100"
                        step="0.5"
                        value={numericThresholds[field] ?? def}
                        onChange={(e) => handleNumericChange(field, Number(e.target.value))}
                        className="w-8 h-4 border-none bg-transparent text-[11px] font-bold focus-visible:ring-0 p-0 text-center dark:text-slate-200"
                      />
                      <span className="text-[11px] text-slate-400 dark:text-slate-500 font-bold">%</span>
                    </div>
                  </div>
                  <Input 
                    type="range" 
                    min="0" 
                    max="100" 
                    step="0.5" 
                    value={numericThresholds[field] ?? def} 
                    onChange={(e) => handleNumericChange(field, Number(e.target.value))}
                    className="h-4 accent-slate-600 dark:accent-slate-400 cursor-pointer"
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="pt-3 border-t border-slate-100 dark:border-[#30363d] flex items-center justify-between">
        <p className="text-[10px] text-slate-400 italic">※ 임계값 이하의 변동은 '단순변동'으로 처리되어 강조되지 않습니다.</p>
        <code className="text-[9px] text-slate-300 dark:text-slate-500 font-mono">회차 변동: 항상 무시됨</code>
      </div>
    </div>
  );
}
