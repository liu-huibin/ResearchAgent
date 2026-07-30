import type { Session, Message, Document, SessionMetrics } from '../types';

const BASE = '/api';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  // Sessions
  createSession: (title?: string) =>
    request<Session>('/sessions', {
      method: 'POST',
      body: JSON.stringify({ title: title || '新会话' }),
    }),

  listSessions: () => request<Session[]>('/sessions'),

  deleteSession: (id: number) =>
    request<void>(`/sessions/${id}`, { method: 'DELETE' }),

  renameSession: (id: number, title: string) =>
    request<Session>(`/sessions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),

  // Messages
  getMessages: (sessionId: number) =>
    request<Message[]>(`/sessions/${sessionId}/messages`),

  getSessionMetrics: (sessionId: number) =>
    request<SessionMetrics>(`/sessions/${sessionId}/metrics`),

  // Documents
  uploadDocument: (sessionId: number, file: File): Promise<Document> => {
    const formData = new FormData();
    formData.append('file', file);
    return fetch(`${BASE}/sessions/${sessionId}/upload`, {
      method: 'POST',
      body: formData,
    }).then((res) => {
      if (!res.ok) throw new Error('上传失败');
      return res.json();
    });
  },

  getSessionDocument: (sessionId: number) =>
    request<Document | null>(`/sessions/${sessionId}/document`),

  getDocumentFileUrl: (documentId: number) =>
    `${BASE}/documents/${documentId}/file`,

  // Knowledge Base
  listKnowledge: () =>
    request<Document[]>('/knowledge/list'),

  deleteKnowledge: (docId: number) =>
    request<void>(`/knowledge/${docId}`, { method: 'DELETE' }),

  uploadKnowledge: (file: File, onProgress?: (pct: number) => void): Promise<Document> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append('file', file);

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText));
        } else if (xhr.status === 409) {
          reject(new Error('文件已存在于知识库中'));
        } else {
          reject(new Error('上传失败'));
        }
      });

      xhr.addEventListener('error', () => reject(new Error('网络错误')));

      xhr.open('POST', `${BASE}/knowledge/upload`);
      xhr.send(formData);
    });
  },

  // SSE
  sendMessageStream: (sessionId: number, content: string) =>
    fetch(`${BASE}/sessions/${sessionId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    }),
};
