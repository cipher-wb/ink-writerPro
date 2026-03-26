/**
 * API 请求工具函数
 */

const BASE = '';  // 开发时由 vite proxy 代理到 FastAPI

export async function fetchJSON(path, params = {}) {
    const url = new URL(path, window.location.origin);
    Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null) url.searchParams.set(k, v);
    });
    const res = await fetch(url.toString());
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
}

/**
 * 订阅 SSE 实时事件流（带指数退避重连）
 * @param {function} onMessage  收到 data 时回调
 * @param {{onOpen?: function, onError?: function}} handlers 连接状态回调
 * @returns {function} 取消订阅函数
 */
export function subscribeSSE(onMessage, handlers = {}) {
    const { onOpen, onError } = handlers;
    const MAX_RETRIES = 10;
    const BASE_DELAY = 1000;   // 1秒
    const MAX_DELAY = 30000;   // 30秒

    let es = null;
    let retryCount = 0;
    let cancelled = false;

    function connect() {
        if (cancelled) return;
        es = new EventSource(`${BASE}/api/events`);

        es.onopen = () => {
            retryCount = 0;  // 连接成功，重置计数
            if (onOpen) onOpen();
        };

        es.onmessage = (e) => {
            try {
                onMessage(JSON.parse(e.data));
            } catch { /* ignore parse errors */ }
        };

        es.onerror = (e) => {
            es.close();
            if (cancelled) return;
            if (onError) onError(e);

            if (retryCount < MAX_RETRIES) {
                const delay = Math.min(MAX_DELAY, BASE_DELAY * Math.pow(2, retryCount));
                retryCount++;
                setTimeout(connect, delay);
            }
        };
    }

    connect();

    return () => {
        cancelled = true;
        if (es) es.close();
    };
}
