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
              try {
                const parsed = JSON.parse(dataLines.join('\n'));
                yield {
                  type: eventType as SSEMessageEvent['type'],
                  ...parsed,
                };
              } catch {
                // Ignore this malformed frame and continue with later events.
              }
            }
            boundary = buffer.indexOf('\n\n');
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
