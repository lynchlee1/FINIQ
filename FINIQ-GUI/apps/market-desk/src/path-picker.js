async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.error || `HTTP ${response.status}`);
  }
  return result;
}

function dispatchPathChange(input) {
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

export async function choosePath({ mode, title, defaultPath = "" }) {
  const payload = await postJson("/api/file-dialog", {
    mode,
    title,
    default_path: defaultPath,
  });
  return payload.path || "";
}

export function bindPathPicker(root = document, { onPicked = null, onError = null } = {}) {
  root.querySelectorAll("[data-path-target][data-dialog-mode]").forEach((button) => {
    button.addEventListener("click", async () => {
      const input = document.getElementById(button.dataset.pathTarget || "");
      if (!input) {
        return;
      }
      const defaultInput = document.getElementById(button.dataset.defaultInput || "");
      const defaultPath = input.value || defaultInput?.value || "";
      const originalText = button.textContent;
      button.disabled = true;
      button.textContent = "여는 중";
      try {
        const path = await choosePath({
          mode: button.dataset.dialogMode,
          title: button.dataset.dialogTitle || "경로 선택",
          defaultPath,
        });
        if (!path) {
          return;
        }
        input.value = path;
        dispatchPathChange(input);
        if (onPicked) {
          await onPicked(input, button);
        }
      } catch (error) {
        if (onError) {
          onError(error, input, button);
          return;
        }
        console.error(error);
      } finally {
        button.disabled = false;
        button.textContent = originalText;
      }
    });
  });
}
