import { useState, useEffect, useRef, useCallback } from 'react';
import MessageList from './MessageList';
import ChatInput from './ChatInput';
import { useSSE } from '../../hooks/useSSE';
import { api } from '../../services/api';
import type { AgentName, Message, Session, SessionMetrics } from '../../types';

interface LiveMetrics {
  status: string;
  promptVariant: string;
  langsmithEnabled: boolean;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  durationMs: number;
}

interface StreamingMessage {
  thought: string;
  content: string;
  toolCalls: { agent?: AgentName; tool: string; input: string; output?: string; is_error?: boolean }[];
  activeAgent: AgentName | null;
  metrics: LiveMetrics | null;
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
  const [sessionMetrics, setSessionMetrics] = useState<SessionMetrics | null>(null);
  const [error, setError] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { stream, abort } = useSSE();

  // Load message history
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      setSessionMetrics(null);
      return;
    }
    setLoading(true);
    Promise.all([
      api.getMessages(sessionId),
      api.getSessionMetrics(sessionId).catch(() => null),
    ])
      .then(([history, metrics]) => {
        setMessages(history);
        setSessionMetrics(metrics);
      })
      .catch(() => {
        setMessages([]);
        setSessionMetrics(null);
      })
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
      const sMsg: StreamingMessage = {
        thought: '',
        content: '',
        toolCalls: [],
        activeAgent: null,
        metrics: null,
        done: false,
      };
      setStreaming(sMsg);

      try {
        for await (const event of stream(realSessionId, content)) {
          switch (event.type) {
            case 'agent':
              sMsg.activeAgent = event.agent || null;
              if (event.agent) sMsg.thought += `\n[${event.agent}]\n`;
              setStreaming({ ...sMsg });
              break;
            case 'thought':
              sMsg.thought += event.content || '';
              setStreaming({ ...sMsg });
              break;
            case 'action':
              sMsg.toolCalls.push({
                agent: event.agent,
                tool: event.tool || 'unknown',
                input: typeof event.input === 'string'
                  ? event.input
                  : JSON.stringify(event.input || {}),
              });
              setStreaming({ ...sMsg });
              break;
            case 'observation': {
              const toolCall = [...sMsg.toolCalls].reverse().find(
                tc => tc.tool === event.tool
                  && tc.agent === event.agent
                  && tc.output === undefined
              );
              if (toolCall) toolCall.output = event.output || '';
              if (toolCall) toolCall.is_error = event.is_error;
              setStreaming({ ...sMsg });
              break;
            }
            case 'token':
              sMsg.content += event.content || '';
              setStreaming({ ...sMsg });
              break;
            case 'metrics':
              sMsg.metrics = {
                status: event.status || 'completed',
                promptVariant: event.prompt_variant || 'phase4-v1',
                langsmithEnabled: Boolean(event.langsmith_enabled),
                inputTokens: event.input_tokens || 0,
                outputTokens: event.output_tokens || 0,
                totalTokens: event.total_tokens || 0,
                durationMs: event.duration_ms || 0,
              };
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
        const [msgs, metrics] = await Promise.all([
          api.getMessages(realSessionId),
          api.getSessionMetrics(realSessionId),
        ]);
        setMessages(msgs);
        setSessionMetrics(metrics);
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
      <div className="px-4 py-2 border-b border-gray-200 shrink-0 flex items-center justify-between gap-3">
        <span className="font-medium text-sm text-gray-700">对话</span>
        {(streaming?.metrics || sessionMetrics?.latest_run) ? (
          <div
            className="text-[11px] text-gray-500 bg-gray-50 border border-gray-200 rounded-md px-2 py-1 text-right"
            title={`Prompt: ${streaming?.metrics?.promptVariant || sessionMetrics?.latest_run?.prompt_variant || '-'} · LangSmith: ${(streaming?.metrics?.langsmithEnabled || sessionMetrics?.latest_run?.langsmith_enabled) ? '已启用' : '本地统计'}`}
          >
            <span className="font-medium text-gray-700">
              本轮 {(streaming?.metrics?.totalTokens ?? sessionMetrics?.latest_run?.total_tokens ?? 0).toLocaleString()} tokens
            </span>
            <span className="mx-1.5 text-gray-300">|</span>
            会话 {(sessionMetrics?.total_tokens ?? 0).toLocaleString()}
          </div>
        ) : (
          <span className="text-[11px] text-gray-400">Token 统计将在对话后显示</span>
        )}
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
