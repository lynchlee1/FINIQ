import { apiPost } from "@/api/client";

export type PathDialogMode = "file" | "folder" | "save";

type PickPathOptions = {
  mode: PathDialogMode;
  title: string;
  defaultPath?: string;
};

type FileDialogResponse = {
  path?: string;
  cancelled?: boolean;
};

export async function pickPath({
  mode,
  title,
  defaultPath = "",
}: PickPathOptions): Promise<string> {
  const data = await apiPost<FileDialogResponse>("/api/file-dialog", { mode, title, default_path: defaultPath });
  return data.path || "";
}
