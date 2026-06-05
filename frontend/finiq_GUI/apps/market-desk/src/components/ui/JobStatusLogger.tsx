import { cn } from "@finiq/ui/utils";
import { Button } from "@finiq/ui";
import { Square } from "lucide-react";

interface JobStatusLoggerProps {
  status: string;
  isErrorStatus: boolean;
  onCancel?: () => void;
  isCancellable?: boolean;
}

export function JobStatusLogger({
  status,
  isErrorStatus,
  onCancel,
  isCancellable = false,
}: JobStatusLoggerProps) {
  return (
    <div className="space-y-3">
      {isCancellable && onCancel && (
        <div className="flex justify-end">
          <Button
            variant="outline"
            onClick={onCancel}
            className="dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-300"
          >
            <Square className="mr-2 h-4 w-4" />
            작업 중단
          </Button>
        </div>
      )}
      <div
        className={cn(
          "min-h-[120px] max-h-[360px] overflow-auto rounded-lg border p-4 font-mono text-xs whitespace-pre-wrap leading-relaxed",
          isErrorStatus
            ? "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-900/40 text-red-700 dark:text-red-300"
            : "bg-slate-50 dark:bg-[#090d12] border-slate-200 dark:border-slate-700 text-slate-700 dark:text-blue-100"
        )}
      >
        {status}
      </div>
    </div>
  );
}
