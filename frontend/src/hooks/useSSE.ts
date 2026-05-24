import { useRef, useCallback } from 'react';
import type { SSEMessageEvent } from '../types';

export function useSSE() {
  const abortRef = useRef<AbortController | null>(null);

  const stream = useCallback(
    async function* (
      sessionId: number,
      content: string
    ): AsyncGenerator<SSEMessageEvent> {
      // Abort previous stream
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const response = await fetch(`/api/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const err = await response.text();
        throw new Error(err);
      }

      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = '';

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          let currentType = '';
          let currentData = '';

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentType = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              currentData = line.slice(6);
              try {
                const parsed = JSON.parse(currentData);
                yield { type: currentType as SSEMessageEvent['type'], ...parsed };
              } catch {
                // skip malformed
              }
              currentType = '';
              currentData = '';
            }
          }
        }
      } finally {
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
