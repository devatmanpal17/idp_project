const LOCAL_API_URL = "http://127.0.0.1:8000/api";

export function apiBaseUrl() {
  const configured = import.meta.env["VITE_API_BASE_URL"]
    ?.trim()
    .replace(/\/$/, "");
  if (configured) return configured;

  if (
    typeof window !== "undefined" &&
    (window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1")
  ) {
    return LOCAL_API_URL;
  }

  return "/api";
}

export function apiUrl(path: string) {
  return `${apiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function apiJSON<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), init);
  } catch {
    throw new Error(
      "The learning engine is offline. Start FastAPI on port 8000.",
    );
  }

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return body as T;
}
