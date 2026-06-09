import { cn } from "@finiq/ui/utils";
import { getChangedFields } from "@/utils/matrixUtils";
import { formatInteger } from "@/lib/format";

interface ChangeLogSidebarProps {
  families: any[];
  selectedFamilyId: string;
  onSelectFamily: (familyId: string) => void;
  hasSearchKeyword: boolean;
}

export function ChangeLogSidebar({ families, selectedFamilyId, onSelectFamily, hasSearchKeyword }: ChangeLogSidebarProps) {
  return (
    <div className="lg:col-span-4 border rounded-xl overflow-hidden bg-white dark:bg-[#0d1117] dark:border-[#30363d] flex flex-col">
      <div className="p-3 bg-slate-50 dark:bg-[#161b22] border-b dark:border-[#30363d] text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
        정정 패밀리 목록
      </div>
      <div className="overflow-auto flex-1 divide-y divide-slate-100 dark:divide-[#30363d] max-h-[600px]">
        {families.length > 0 ? (
          families.map((family: any) => {
            const isSelected = selectedFamilyId === family.family_id;
            const displayChangedFields = getChangedFields(family);
            const displayCount = family.has_details ? displayChangedFields.length : (family.changed_fields ?? 0);
            
            return (
              <button 
                key={family.family_id}
                onClick={() => onSelectFamily(family.family_id)}
                className={cn(
                  "w-full text-left p-4 hover:bg-slate-50 dark:hover:bg-[#161b22] transition-colors group relative",
                  isSelected ? "bg-blue-50/50 dark:bg-[#161b22]" : ""
                )}
              >
                {isSelected && <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-600 dark:bg-blue-500" />}
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <strong className={cn(
                      "text-[13px] leading-snug flex-1 transition-colors",
                      isSelected ? "text-blue-900 dark:text-slate-100" : "text-slate-700 dark:text-slate-200"
                    )}>
                      {family.title || family.family_id}
                    </strong>
                    <div className={cn(
                      "shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase",
                      displayCount > 0 
                        ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400" 
                        : "bg-slate-100 text-slate-400 dark:bg-[#30363d] dark:text-slate-500"
                    )}>
                      {displayCount > 0 ? `Changed ${formatInteger(displayCount)}` : "No Change"}
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2 text-[10px] text-slate-400 dark:text-slate-500 font-medium">
                    <code className="bg-slate-50 dark:bg-[#161b22] px-1 rounded border dark:border-[#30363d]">{family.family_id}</code>
                    <span>•</span>
                    <span>문서 {formatInteger(family.record_count)}</span>
                  </div>

                  {displayCount > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {displayChangedFields.slice(0, 5).map((f: string) => (
                        <span key={f} className="px-1.5 py-0.5 rounded bg-blue-50 dark:bg-[#161b22] text-blue-600 dark:text-blue-400 text-[9px] font-medium border border-blue-100 dark:border-[#30363d]">{f}</span>
                      ))}
                      {displayChangedFields.length > 5 && (
                        <span className="text-[9px] text-slate-400 dark:text-slate-600 font-medium self-center ml-0.5">+{formatInteger(displayChangedFields.length - 5)}</span>
                      )}
                    </div>
                  )}
                </div>
              </button>
            );
          })
        ) : (
          <div className="p-8 text-center text-slate-400 dark:text-slate-600 text-sm">
            {hasSearchKeyword ? "검색 결과가 없습니다." : "파싱 결과를 불러오세요."}
          </div>
        )}
      </div>
    </div>
  );
}
