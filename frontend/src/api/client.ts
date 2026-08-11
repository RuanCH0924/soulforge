/** 统一 fetch 封装：解包 {data, meta}，错误抛 ApiError {code, message, details} */

export class ApiError extends Error {
  code: string;
  details?: unknown;
  constructor(code: string, message: string, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.details = details;
  }
}

/** 文件路径是 URL 的一部分：每个路径段单独编码，保留 "/" 分隔符 */
export function encodePath(path: string): string {
  return path
    .split('/')
    .map((seg) => encodeURIComponent(seg))
    .join('/');
}

interface RequestOptions {
  json?: unknown;
  form?: FormData;
}

interface Envelope<T> {
  data: T;
  meta?: unknown;
}

interface ErrorEnvelope {
  error?: { code?: string; message?: string; details?: unknown };
}

export async function request<T>(method: string, url: string, opts?: RequestOptions): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers: opts?.form ? undefined : opts?.json !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: opts?.form ? opts.form : opts?.json !== undefined ? JSON.stringify(opts.json) : undefined,
    });
  } catch {
    throw new ApiError('NETWORK_ERROR', '无法连接服务器，请确认后端已启动（端口 8848）');
  }

  let json: unknown = null;
  try {
    json = await res.json();
  } catch {
    // 非 JSON 响应（如导出下载），交给调用方处理
  }

  if (!res.ok || (json && typeof json === 'object' && 'error' in (json as object))) {
    const err = (json as ErrorEnvelope | null)?.error;
    throw new ApiError(
      err?.code ?? 'HTTP_ERROR',
      err?.message ?? `请求失败（HTTP ${res.status}）`,
      err?.details,
    );
  }
  return (json as Envelope<T>).data;
}

/** 下载二进制文件（导出 tar.gz），从 Content-Disposition 取文件名 */
export async function downloadFile(url: string, fallbackName: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new ApiError('NETWORK_ERROR', '无法连接服务器，请确认后端已启动（端口 8848）');
  }
  if (!res.ok) {
    throw new ApiError('HTTP_ERROR', `下载失败（HTTP ${res.status}）`);
  }
  const blob = await res.blob();
  const disposition = res.headers.get('Content-Disposition') ?? '';
  const m = disposition.match(/filename="?([^";]+)"?/i);
  const name = m?.[1] || fallbackName;
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = name;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
}
