export const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
export class ApiError extends Error {
  constructor(public status: number, message: string, public details?: unknown) { super(message); }
}
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, credentials: 'include', headers: { ...(init?.body instanceof FormData ? {} : {'Content-Type': 'application/json'}), ...init?.headers } });
  } catch {
    throw new ApiError(0, 'Cannot reach the portal server. Check that the API is running.');
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, body?.message || 'The request could not be completed.', body?.details);
  return body as T;
}
