const apiBaseUrl = (process.env.FINIQ_API_BASE_URL || "http://127.0.0.1:8765").replace(/\/$/, "");
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 3000);

try {
  const response = await fetch(`${apiBaseUrl}/api/config`, {
    signal: controller.signal,
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
} catch (error) {
  const detail = error?.name === "AbortError" ? "request timed out" : error?.message || String(error);
  console.error(`Market Desk backend is not reachable at ${apiBaseUrl}/api/config (${detail}).`);
  console.error("Start the backend API first, or set FINIQ_API_BASE_URL to the running backend.");
  process.exit(1);
} finally {
  clearTimeout(timeout);
}
