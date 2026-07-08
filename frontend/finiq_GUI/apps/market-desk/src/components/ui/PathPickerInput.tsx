import { PathPickerInput as WebAppPathPickerInput } from "@finiq/web-app";
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
  disabled = false,
  ...props
}: PathPickerInputProps) {
  return (
    <WebAppPathPickerInput
      {...props}
      disabled={disabled}
      pickPath={pickPath}
    />
  );
}
