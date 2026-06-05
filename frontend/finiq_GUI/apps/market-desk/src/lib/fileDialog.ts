export type PathDialogMode = "file" | "folder" | "save";

type PickPathOptions = {
  mode: PathDialogMode;
  title: string;
  defaultPath?: string;
};

type FileDialogResponse = {
  path?: string;
  cancelled?: boolean;
  detail?: string;
};

export async function pickPath({
  mode,
  title,
  defaultPath = "",
}: PickPathOptions): Promise<string> {
  const response = await fetch("/api/file-dialog", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, title, default_path: defaultPath }),
  });
  const data = (await response.json()) as FileDialogResponse;
  if (!response.ok) {
    throw new Error(data.detail || "경로 선택에 실패했습니다.");
  }
  return data.path || "";
}
