import MessageBubble from './MessageBubble';
import type { Message } from '../../types';

interface StreamingMessage {
  thought: string;
  content: string;
  toolCalls: { tool: string; input: string; output?: string }[];
  done: boolean;
}

interface MessageListProps {
  messages: Message[];
  streaming: StreamingMessage | null;
  error: string;
}

export default function MessageList({ messages, streaming, error }: MessageListProps) {
  return (
    <div className="px-3 py-2 space-y-3">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      {/* Streaming message */}
      {streaming && (
        <div className="flex flex-col gap-1">
          {streaming.thought && (
            <MessageBubble
              message={{
                id: -1,
                session_id: 0,
                role: 'assistant',
                content: null,
                thought: streaming.thought,
                tool_calls: streaming.toolCalls,
                created_at: '',
              }}
              isStreaming
            />
          )}
          {streaming.content && (
            <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
              <div className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
                {streaming.content}
                {!streaming.done && <span className="inline-block w-2 h-4 bg-gray-600 animate-pulse ml-0.5 align-middle" />}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
          {error}
        </div>
      )}
    </div>
  );
}
