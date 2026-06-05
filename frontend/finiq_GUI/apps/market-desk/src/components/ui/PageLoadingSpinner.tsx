import { Loader2 } from "lucide-react";

interface PageLoadingSpinnerProps {
  message?: string;
}

export function PageLoadingSpinner({ message = "데이터를 불러오는 중입니다..." }: PageLoadingSpinnerProps) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4">
      <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      <p className="text-slate-500 font-medium">{message}</p>
    </div>
  );
}
