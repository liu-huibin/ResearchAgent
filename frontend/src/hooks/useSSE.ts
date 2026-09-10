import { useRef, useCallback, useEffect } from 'react';
import type { SSEMessageEvent } from '../types';
import { apiHeaders, authorizedFetch } from '../services/security';

export function useSSE() {
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => () => abortRef.current?.abort(), []);

  const stream = useCallback(
    async function* (
      sessionId: number,
      content: string
    ): AsyncGenerator<SSEMessageEvent> {
      // Abort previous stream
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const response = await authorizedFetch(`/api/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: apiHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ content }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const err = await response.text();
        throw new Error(err);
      }

      const responseTraceId = response.headers.get('X-Trace-ID');
      if (responseTraceId) {
        yield { type: 'start', trace_id: responseTraceId };
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('服务器未返回数据流');

      const decoder = new TextDecoder();
      let buffer = '';
      let completed = false;

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer = (buffer + decoder.decode(value, { stream: true }))
            .replace(/\r\n/g, '\n');

          let boundary = buffer.indexOf('\n\n');
          while (boundary !== -1) {
            const block = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            let eventType = '';
            const dataLines: string[] = [];

            for (const line of block.split('\n')) {
              if (line.startsWith('event:')) {
                eventType = line.slice(6).trim();
              } else if (line.startsWith('data:')) {
                dataLines.push(line.slice(5).trimStart());
              }
            }

            if (eventType && dataLines.length > 0) {
              const parsed = JSON.parse(dataLines.join('\n'));
              if (eventType === 'done' && parsed.persisted === true) completed = true;
              yield {
                  ...parsed,
                  type: eventType as SSEMessageEvent['type'],
              };
              if (completed) return;
            }
            boundary = buffer.indexOf('\n\n');
          }
        }
        if (!completed) throw new Error('连接中断，正在确认回答是否已保存');
      } finally {
        controller.abort();
        reader.releaseLock();
      }
    },
    []
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { stream, abort };
}
