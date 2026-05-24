import { useState, useEffect, useRef, useCallback } from 'react';
import MessageList from './MessageList';
import ChatInput from './ChatInput';
import { useSSE } from '../../hooks/useSSE';
import { api } from '../../services/api';
import type { Message, Session } from '../../types';

interface StreamingMessage {
  thought: string;
  content: string;
  toolCalls: { tool: string; input: string; output?: string }[];
  done: boolean;
}

interface ChatPanelProps {
  sessionId: number | null;
  onSessionUpdate: () => void;
  onCommitPending: (tempId: number) => Promise<Session | undefined>;
}

export default function ChatPanel({ sessionId, onSessionUpdate, onCommitPending }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState<StreamingMessage | null>(null);
  const [error, setError] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { stream, abort } = useSSE();

  // Load message history
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      return;
    }
    setLoading(true);
    api.getMessages(sessionId)
      .then(setMessages)
      .catch(() => setMessages([]))
      .finally(() => setLoading(false));
  }, [sessionId]);

  // Auto scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming]);

  const handleSend = useCallback(
    async (content: string) => {
      if (!sessionId || !content.trim()) return;
      setError('');

      // Commit pending session on first message
      let realSessionId = sessionId;
      if (sessionId < 0) {
        const real = await onCommitPending(sessionId);
        if (!real) {
          setError('创建会话失败');
          return;
        }
        realSessionId = real.id;
      }

      // Add user message optimistically
      const userMsg: Message = {
        id: Date.now(),
        session_id: realSessionId,
        role: 'user',
        content,
        thought: null,
        tool_calls: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);

      // Start streaming
      const sMsg: StreamingMessage = { thought: '', content: '', toolCalls: [], done: false };
      setStreaming(sMsg);

      try {
        for await (const event of stream(realSessionId, content)) {
          switch (event.type) {
            case 'thought':
              sMsg.thought += (event.content || '') + '\n';
              setStreaming({ ...sMsg });
              break;
            case 'action':
              sMsg.toolCalls.push({
                tool: event.tool || 'unknown',
                input: event.input || '',
              });
              setStreaming({ ...sMsg });
              break;
            case 'observation': {
              const lastTc = sMsg.toolCalls[sMsg.toolCalls.length - 1];
              if (lastTc) lastTc.output = event.output || '';
              setStreaming({ ...sMsg });
              break;
            }
            case 'token':
              sMsg.content += event.content || '';
              setStreaming({ ...sMsg });
              break;
            case 'error':
              setError(event.content || '发生错误');
              sMsg.done = true;
              setStreaming({ ...sMsg });
              break;
            case 'done':
              sMsg.done = true;
              setStreaming({ ...sMsg });
              break;
          }
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : '发送失败';
        setError(msg);
      }

      // Load real messages from server
      try {
        const msgs = await api.getMessages(realSessionId);
        setMessages(msgs);
      } catch {
        // keep optimistic
      }
      setStreaming(null);
      onSessionUpdate();
    },
    [sessionId, stream, onSessionUpdate, onCommitPending]
  );

  if (!sessionId) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        请选择会话开始对话
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 font-medium text-sm text-gray-700 shrink-0">
        对话
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-center text-gray-400 text-sm">加载消息...</div>
        ) : (
          <MessageList messages={messages} streaming={streaming} error={error} />
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <ChatInput onSend={handleSend} onStop={abort} streaming={!!streaming && !streaming.done} />
    </div>
  );
}
