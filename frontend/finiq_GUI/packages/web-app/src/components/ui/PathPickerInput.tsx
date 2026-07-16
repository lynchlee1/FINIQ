import { File, FolderOpen, Save } from "lucide-react";
import { Button, Input } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";

export type PathDialogMode = "folder" | "file" | "save";

export type PickPathOptions = {
  mode: PathDialogMode;
  title: string;
  defaultPath?: string;
};

type PathPickerInputProps = {
  mode: PathDialogMode;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  title?: string;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  onError?: (err: Error) => void;
  pickPath: (options: PickPathOptions) => Promise<string>;
};

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
  pickPath,
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
        if (onBlur) onBlur();
      }
    } catch (err) {
      if (onError) onError(err instanceof Error ? err : new Error(String(err)));
    }
  };

  return (
    <div className={cn("flex min-w-0 gap-2", className)}>
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
        placeholder={placeholder}
        disabled={disabled}
        className="h-10 flex-1 text-sm dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 dark:placeholder:text-slate-600"
      />
      <Button
        type="button"
        variant="outline"
        size="icon-lg"
        aria-label={title}
        title={title}
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
