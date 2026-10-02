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

export async function apiJSON<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = !init?.method || init.method.toUpperCase() === "GET"
    ? 15_000
    : 300_000,
): Promise<T> {
  const controller = new AbortController();
  const signal = init?.signal;
  const cancel = () => controller.abort(signal?.reason);
  if (signal?.aborted) cancel();
  else signal?.addEventListener("abort", cancel, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    let response: Response;
    try {
      response = await fetch(apiUrl(path), {
        ...init,
        signal: controller.signal,
      });
    } catch (error) {
      if (controller.signal.aborted) throw error;
      throw new Error(
        "The learning engine is unreachable. Check the backend and API address.",
      );
    }

    let body;
    try {
      body = await response.json();
    } catch (error) {
      if (controller.signal.aborted) throw error;
      throw new Error(
        `The API returned invalid JSON (${response.status}). Check the backend address.`,
      );
    }
    if (!response.ok) {
      const detail =
        typeof body?.detail === "string"
          ? body.detail
          : Array.isArray(body?.detail)
            ? body.detail
                .map(
                  (issue: { loc?: unknown[]; msg?: string }) =>
                    `${issue.loc?.join(".") || "Request"}: ${issue.msg || "Invalid value"}`,
                )
                .join("; ")
            : `Request failed (${response.status})`;
      throw new Error(detail);
    }
    if (body === null || typeof body !== "object") {
      throw new Error("The API returned an invalid JSON payload.");
    }
    return body as T;
  } catch (error) {
    if (signal?.aborted) {
      throw (
        signal.reason ?? new DOMException("Request cancelled", "AbortError")
      );
    }
    if (timedOut) {
      throw new Error(
        "The request timed out. Check the backend and Ollama. It may still finish on the server; refresh before retrying.",
      );
    }
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
}
