export async function savePathSetting(partialPayload) {
  const response = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(partialPayload),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

export function bindPathSetting(input, buildPayload, onError) {
  const save = async () => {
    if (input) {
      input.dataset.touched = "true";
    }
    try {
      await savePathSetting(buildPayload(input));
    } catch (error) {
      if (onError) {
        onError(error);
        return;
      }
      console.error(error);
    }
  };
  input?.addEventListener("change", save);
  input?.addEventListener("blur", save);
  input?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    save();
  });
}
