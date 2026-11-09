// Access-токен живёт только в памяти: скрипт со страницы не найдёт его в localStorage.
// После перезагрузки страницы новый берём по refresh-cookie
let accessToken: string | null = null;
let onSessionLost: () => void = () => {};

export function setSessionLostHandler(handler: () => void) {
  onSessionLost = handler;
}

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function errorFrom(response: Response): Promise<ApiError> {
  let message = 'Что-то пошло не так. Попробуйте ещё раз';
  try {
    const body = await response.json();
    if (typeof body.detail === 'string') message = body.detail;
    else if (Array.isArray(body.detail)) message = 'Проверьте правильность заполнения полей';
  } catch {
    // Ответ не JSON (например, ошибка прокси) — оставляем общее сообщение
  }
  return new ApiError(response.status, message);
}

let refreshing: Promise<boolean> | null = null;

async function doRefresh(): Promise<boolean> {
  const response = await fetch('/api/auth/refresh', { method: 'POST' });
  if (!response.ok) {
    accessToken = null;
    return false;
  }
  accessToken = (await response.json()).access_token;
  return true;
}

export function refreshSession(): Promise<boolean> {
  // Один refresh на вкладку: параллельные запросы ждут общий результат
  refreshing ??= (async () => {
    try {
      // Web Locks — очередь между вкладками. Refresh-токен одноразовый: две вкладки
      // с одной cookie одновременно выглядели бы для сервера как кража токена.
      // Вне HTTPS (кроме localhost) API нет — тогда обходимся без очереди
      if (navigator.locks) {
        return await navigator.locks.request('walletly-refresh', doRefresh);
      }
      return await doRefresh();
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

type Query = Record<string, string | number | boolean | undefined | null>;

interface Options {
  method?: string;
  body?: unknown;
  form?: FormData;
  query?: Query;
  // Для входа и регистрации 401 означает «неверный пароль», а не истёкшую сессию
  noRefresh?: boolean;
}

function buildUrl(path: string, query?: Query) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const suffix = params.toString();
  return `/api${path}${suffix ? `?${suffix}` : ''}`;
}

async function send(path: string, options: Options) {
  const headers: Record<string, string> = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  return fetch(buildUrl(path, options.query), {
    method: options.method ?? 'GET',
    headers,
    body: options.form ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
  });
}

async function request(path: string, options: Options): Promise<Response> {
  let response = await send(path, options);
  if (response.status === 401 && !options.noRefresh) {
    if (await refreshSession()) {
      response = await send(path, options);
    } else {
      onSessionLost();
    }
  }
  if (!response.ok) throw await errorFrom(response);
  return response;
}

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const response = await request(path, options);
  if (response.status === 204) return undefined as T;
  return response.json();
}

// Обычная ссылка на файл не подойдёт: access-токен передаётся только в заголовке
export async function downloadFile(path: string, filename: string, query?: Query): Promise<void> {
  const response = await request(path, { query });
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'Не удалось связаться с сервером';
}
