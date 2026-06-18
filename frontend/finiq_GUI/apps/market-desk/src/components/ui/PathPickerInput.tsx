import { FolderOpen, File, Save } from "lucide-react";
import { Button, Input } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import { pickPath } from "@/lib/fileDialog";

interface PathPickerInputProps {
  mode: "folder" | "file" | "save";
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  title?: string;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  onError?: (err: Error) => void;
}

export function PathPickerInput({
  mode,
  value,
  onChange,
  onBlur,
  title = "경로 선택",
  placeholder,
  className,
  disabled = false,
  onError,
}: PathPickerInputProps) {
  const handlePickPath = async () => {
    try {
      const path = await pickPath({
        mode,
        title,
        defaultPath: value || "",
      });
      if (path) {
        onChange(path);
        if (onBlur) onBlur(); // Auto trigger save on pick
      }
    } catch (err: any) {
      if (onError) onError(err);
    }
  };

  return (
    <div className={cn("flex min-w-0 gap-2", className)}>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder={placeholder}
        disabled={disabled}
        className="h-10 flex-1 text-sm dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 dark:placeholder:text-slate-600"
      />
      <Button
        variant="outline"
        size="icon-lg"
        onClick={handlePickPath}
        disabled={disabled}
        className="dark:border-[#30363d] dark:hover:bg-[#21262d]"
      >
        {mode === "folder" ? (
          <FolderOpen className="h-4 w-4 dark:text-slate-400" />
        ) : mode === "save" ? (
          <Save className="h-4 w-4 dark:text-slate-400" />
        ) : (
          <File className="h-4 w-4 dark:text-slate-400" />
        )}
      </Button>
    </div>
  );
}
