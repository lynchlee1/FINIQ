import { Loader2, CheckCircle2 } from "lucide-react";
import { cn } from "@finiq/ui/utils";
import { getMatrixData, stableJson, parseKoreanDate, parseNumericValue, formatValueWithField } from "@/utils/matrixUtils";
import { useSettingsStore } from "@/store/useSettingsStore";
import { DATE_FIELDS_CONFIG, NUMERIC_FIELDS_CONFIG } from "./ChangeLogSettings";

interface ChangeLogMatrixProps {
  selectedFamily: any | null;
}

export function ChangeLogMatrix({ selectedFamily }: ChangeLogMatrixProps) {
  const { change_log_date_thresholds, change_log_numeric_thresholds } = useSettingsStore();

  const dateThresholds = change_log_date_thresholds || Object.fromEntries(DATE_FIELDS_CONFIG.map(c => [c.field, c.default]));
  const numericThresholds = change_log_numeric_thresholds || Object.fromEntries(NUMERIC_FIELDS_CONFIG.map(c => [c.field, c.default]));

  return (
    <div className="lg:col-span-6 border rounded-xl bg-slate-50/50 dark:bg-[#0d1117] dark:border-[#30363d] overflow-hidden flex flex-col min-h-[600px]">
      {selectedFamily ? (
        <>
          <div className="p-6 bg-white dark:bg-[#0d1117] border-b dark:border-[#30363d] space-y-1">
            <div className="flex items-center gap-2">
              <code className="text-[11px] text-slate-400 dark:text-slate-500 font-mono">{selectedFamily.family_id}</code>
            </div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-200 line-clamp-1">
              {selectedFamily.records?.at(-1)?.title || selectedFamily.title}
            </h3>
          </div>

          <div className="flex-1 overflow-auto p-6">
            {!selectedFamily.has_details ? (
              <div className="h-full flex flex-col items-center justify-center space-y-4 py-12">
                <Loader2 className="h-8 w-8 animate-spin text-blue-500 dark:text-blue-400" />
                <div className="text-center">
                  <p className="text-sm font-bold text-slate-900 dark:text-slate-200">상세 변동 내역 분석 중</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">문서 간 데이터 차이를 대조하고 있습니다...</p>
                </div>
              </div>
            ) : (() => {
              const data = getMatrixData(selectedFamily);
              if (!data || data.fields.length === 0) {
                return (
                  <div className="h-full flex flex-col items-center justify-center text-center space-y-3 py-24">
                    <CheckCircle2 className="h-12 w-12 text-emerald-500 dark:text-emerald-500" />
                    <div>
                      <p className="text-sm font-bold text-slate-900 dark:text-slate-200">변동 사항 없음</p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">모든 비교 필드가 이전 버전과 동일합니다.</p>
                    </div>
                  </div>
                );
              }

              return (
                <div className="border rounded-lg bg-white dark:bg-[#0d1117] dark:border-[#30363d] shadow-sm overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-max text-xs border-collapse">
                      <thead className="bg-slate-50 dark:bg-[#161b22] border-b dark:border-[#30363d]">
                        <tr>
                          <th className="px-4 py-3 text-left font-bold text-slate-500 dark:text-slate-400 w-32 min-w-[128px] shrink-0 border-r dark:border-[#30363d] bg-slate-50/80 dark:bg-[#161b22]/80 sticky left-0 z-20">변동 필드</th>
                          {data.records.map((r: any, i: number) => (
                            <th key={`${r.acpt_no}-${i}`} className="px-4 py-3 text-left w-[168px] min-w-[168px] border-r dark:border-[#30363d] last:border-r-0">
                              <div className="flex flex-col gap-0.5">
                                <span className="text-blue-600 dark:text-blue-400 font-bold">#{i + 1} {i === 0 ? "(Original)" : i === data.records.length - 1 ? "(Latest)" : ""}</span>
                                <code className="text-[10px] text-slate-400 dark:text-slate-500 font-mono">{r.acpt_no}</code>
                              </div>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-[#30363d]">
                        {data.fields.map((field: string) => (
                          <tr key={field} className="group">
                            <td className="px-4 py-4 font-bold text-slate-700 dark:text-slate-300 border-r dark:border-[#30363d] bg-slate-50/30 dark:bg-[#161b22]/30 sticky left-0 group-hover:bg-slate-100 dark:group-hover:bg-[#161b22] transition-colors z-10 break-all w-32 min-w-[128px]">
                              {field}
                            </td>
                            {data.matrix[field].map((val: any, i: number) => {
                              const prevVal = i > 0 ? data.matrix[field][i-1] : null;
                              const isChanged = i > 0 && stableJson(val) !== stableJson(prevVal);
                              
                              let changeType: 'none' | 'minor' | 'major' = 'none';
                              if (isChanged) {
                                changeType = 'major';
                                
                                const dateThreshold = dateThresholds[field];
                                const numThreshold = numericThresholds[field];

                                if (dateThreshold !== undefined) {
                                  const d1 = parseKoreanDate(val);
                                  const d2 = parseKoreanDate(prevVal);
                                  if (!isNaN(d1) && !isNaN(d2) && Math.abs(d1 - d2) <= dateThreshold * 24 * 3600 * 1000) changeType = 'minor';
                                } else if (numThreshold !== undefined) {
                                  const n1 = parseNumericValue(val);
                                  const n2 = parseNumericValue(prevVal);
                                  if (!isNaN(n1) && !isNaN(n2) && n1 !== 0) {
                                    const diffPercent = Math.abs((n1 - n2) / n1) * 100;
                                    if (diffPercent <= numThreshold) changeType = 'minor';
                                  }
                                }
                              }

                              return (
                                <td 
                                  key={i} 
                                  className={cn(
                                    "px-4 py-4 border-r dark:border-[#30363d] last:border-r-0 align-top transition-colors break-words w-[168px] min-w-[168px]",
                                    changeType === 'major' ? "bg-amber-50/50 dark:bg-amber-900/10" : changeType === 'minor' ? "bg-slate-50/50 dark:bg-slate-800/10" : ""
                                  )}
                                >
                                  <div className="space-y-1">
                                    {changeType === 'major' && (
                                      <div className="text-[10px] font-bold text-amber-600 dark:text-amber-500 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                                        <div className="w-1.5 h-1.5 rounded-full bg-amber-500 dark:bg-amber-400 animate-pulse" />
                                        Modified
                                      </div>
                                    )}
                                    {changeType === 'minor' && (
                                      <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                                        <div className="w-1 h-1 rounded-full bg-slate-400 dark:bg-slate-500" />
                                        Minor
                                      </div>
                                    )}
                                    <div className="whitespace-pre-wrap leading-relaxed text-[11px] text-slate-700 dark:text-slate-300">
                                      {formatValueWithField(val, field)}
                                    </div>
                                  </div>
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })()}
          </div>
        </>
      ) : (
        <div className="h-full flex flex-col items-center justify-center text-center space-y-4 p-8 text-slate-500 dark:text-slate-400">
          <p className="text-sm">목록에서 정정 패밀리를 선택하면<br/>상세 변동 내역이 이곳에 표시됩니다.</p>
        </div>
      )}
    </div>
  );
}
