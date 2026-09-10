const TOKEN_KEY = 'researchmate.apiToken';
const TOKEN_HEADER = 'X-ResearchMate-Token';

export function getApiToken(): string {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function setApiToken(token: string): void {
  const normalized = token.trim();
  if (normalized) {
    window.sessionStorage.setItem(TOKEN_KEY, normalized);
  } else {
    window.sessionStorage.removeItem(TOKEN_KEY);
  }
}

export function apiHeaders(initial?: HeadersInit): Headers {
  const headers = new Headers(initial);
  const token = getApiToken();
  if (token) headers.set(TOKEN_HEADER, token);
  return headers;
}

async function fetchWithCurrentToken(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  return fetch(input, { ...init, headers: apiHeaders(init?.headers) });
}

/**
 * Fetch an API resource and, when a remote deployment requires a token, ask
 * once and keep it only for this browser tab. The token is never put in a URL
 * or in the Vite bundle.
 */
export async function authorizedFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const tokenBefore = getApiToken();
  let response = await fetchWithCurrentToken(input, init);
  if (response.status !== 401) return response;

  const currentToken = getApiToken();
  if (currentToken && currentToken !== tokenBefore) {
    return fetchWithCurrentToken(input, init);
  }

  const entered = window.prompt('此服务需要 API Token（仅保存在当前标签页）');
  if (!entered) return response;
  setApiToken(entered);
  response = await fetchWithCurrentToken(input, init);
  return response;
}
