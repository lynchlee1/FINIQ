import { FolderOpen, File, Save } from "lucide-react";
import { Button, Input } from "@finiq/ui";
import { pickPath } from "@/lib/fileDialog";

interface PathPickerInputProps {
  mode: "folder" | "file" | "save";
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  title?: string;
  placeholder?: string;
  className?: string;
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
    <div className={`flex gap-2 ${className || ""}`}>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder={placeholder}
        className="flex-1 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
      />
      <Button
        variant="outline"
        size="icon"
        onClick={handlePickPath}
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
