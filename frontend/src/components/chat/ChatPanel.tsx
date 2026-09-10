import { useState, useEffect, useRef, useCallback } from 'react';
import MessageList from './MessageList';
import ChatInput from './ChatInput';
import { useSSE } from '../../hooks/useSSE';
import { api } from '../../services/api';
import type { AgentName, Message, Session, SessionMetrics, ToolCall } from '../../types';

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
  content: string;
  toolCalls: ToolCall[];
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
  const currentSession = useRef(sessionId);
  useEffect(() => { currentSession.current = sessionId; }, [sessionId]);
  const sending = useRef<number | null>(null);
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; abort(); }, [abort]);

  // Load message history
  useEffect(() => {
    let stale = false;
    if (sending.current !== null && (
      sending.current === sessionId || (sending.current < 0 && sessionId !== null && sessionId > 0)
    )) return;
    generation.current++;
    abort();
    sending.current = null;
    setStreaming(null);
    setError('');
    if (!sessionId || sessionId < 0) {
      setMessages([]);
      setSessionMetrics(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    Promise.all([
      api.getMessages(sessionId),
      api.getSessionMetrics(sessionId).catch(() => null),
    ])
      .then(([history, metrics]) => {
        if (stale) return;
        setMessages(history);
        setSessionMetrics(metrics);
      })
      .catch(() => {
        if (stale) return;
        setMessages([]);
        setSessionMetrics(null);
      })
      .finally(() => { if (!stale) setLoading(false); });
    return () => { stale = true; };
  }, [sessionId, abort]);

  // Auto scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming]);

  const handleSend = useCallback(
    async (content: string) => {
      if (!sessionId || !content.trim() || sending.current !== null || loading || streaming) return;
      sending.current = sessionId;
      const requestGeneration = ++generation.current;
      const active = () => generation.current === requestGeneration;
      setError('');

      // Commit pending session on first message
      let realSessionId = sessionId;
      if (sessionId < 0) {
        let real: Session | undefined;
        try { real = await onCommitPending(sessionId); } catch { /* handled below */ }
        if (!active()) return;
        if (!real) {
          setError('创建会话失败');
          sending.current = null;
          return;
        }
        const selected = currentSession.current;
        if (selected !== sessionId && selected !== real.id) {
          generation.current++;
          sending.current = null;
          return;
        }
        realSessionId = real.id;
        sending.current = realSessionId;
      }

      // Add user message optimistically
      const userMsg: Message = {
        id: Date.now(),
        session_id: realSessionId,
        role: 'user',
        content,
        tool_calls: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);

      // Start streaming
      const sMsg: StreamingMessage = {
        content: '',
        toolCalls: [],
        activeAgent: null,
        metrics: null,
        done: false,
      };
      setStreaming(sMsg);
      let traceId: string | undefined;
      let savedMessageId: number | undefined;
      let terminalStatus = '';
      const finishStage = (status: 'succeeded' | 'failed') => {
        const stage = [...sMsg.toolCalls].reverse().find(
          item => item.kind === 'stage' && item.status === 'running'
        );
        if (stage) stage.status = status;
      };

      try {
        for await (const event of stream(realSessionId, content)) {
          if (!active() || (currentSession.current !== realSessionId && currentSession.current !== sessionId)) break;
          if (event.trace_id) traceId = event.trace_id;
          switch (event.type) {
            case 'agent':
              finishStage('succeeded');
              sMsg.activeAgent = event.agent || null;
              sMsg.toolCalls.push({
                kind: 'stage',
                agent: event.agent,
                stage: event.stage || 'unknown',
                detail: event.detail,
                status: 'running',
              });
              setStreaming({ ...sMsg });
              break;
            case 'report': {
              const stage = [...sMsg.toolCalls].reverse().find(
                item => item.kind === 'stage'
                  && item.agent === event.agent
                  && item.stage === event.stage
              );
              if (stage && event.content) {
                stage.report = event.content;
                stage.status = 'succeeded';
              }
              setStreaming({ ...sMsg });
              break;
            }
            case 'action':
              sMsg.toolCalls.push({
                kind: 'tool',
                agent: event.agent,
                tool: event.tool || 'unknown',
                status: 'running',
              });
              setStreaming({ ...sMsg });
              break;
            case 'observation': {
              const toolCall = [...sMsg.toolCalls].reverse().find(
                  tc => (tc.kind ?? 'tool') === 'tool'
                  && tc.tool === event.tool
                  && tc.agent === event.agent
                  && tc.status === 'running'
              );
              if (toolCall) toolCall.status = event.is_error ? 'failed' : 'succeeded';
              if (toolCall) toolCall.is_error = event.is_error;
              setStreaming({ ...sMsg });
              break;
            }
            case 'token':
              sMsg.content += event.content || '';
              setStreaming({ ...sMsg });
              break;
            case 'metrics':
              finishStage(event.status === 'completed' ? 'succeeded' : 'failed');
              sMsg.activeAgent = null;
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
              finishStage('failed');
              sMsg.activeAgent = null;
              setError(event.content || '发生错误');
              setStreaming({ ...sMsg });
              break;
            case 'done':
              finishStage(event.status === 'completed' ? 'succeeded' : 'failed');
              sMsg.activeAgent = null;
              savedMessageId = event.message_id;
              terminalStatus = event.status || '';
              setStreaming({ ...sMsg });
              break;
          }
        }
      } catch (err: unknown) {
        if (!active()) return;
        const msg = err instanceof Error ? err.message : '发送失败';
        setError(err instanceof DOMException && err.name === 'AbortError' ? '已停止，正在确认保存状态' : msg);
      }

      // Load real messages from server
      for (let attempt = 0; attempt < 6 && active(); attempt++) {
       try {
        const [msgs, metrics] = await Promise.all([
          api.getMessages(realSessionId),
          api.getSessionMetrics(realSessionId),
        ]);
        if (!active()) return;
        const run = metrics.runs.find(r => r.trace_id === traceId && r.status !== 'running');
        const confirmedId = savedMessageId ?? run?.assistant_message_id;
        if (!confirmedId || !msgs.some(m => m.id === confirmedId)) {
          await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
          continue;
        }
        setMessages(msgs);
        setSessionMetrics(metrics);
        setStreaming(null);
        const status = run?.status || terminalStatus;
        setError(status && status !== 'completed' ? `本轮已结束并保存（${status}）` : '');
        sending.current = null;
        onSessionUpdate();
        return;
       } catch {
        // keep optimistic
        await new Promise(resolve => setTimeout(resolve, 500));
       }
      }
      if (active()) {
        sMsg.done = true;
        sMsg.activeAgent = null;
        sMsg.toolCalls.forEach(t => { if (t.status === 'running') t.status = 'failed'; });
        setStreaming({ ...sMsg });
        setError('尚未确认保存。当前回答已保留，请复制备份或重新打开会话确认；不要重复发送。');
        sending.current = null;
      }
    },
    [sessionId, stream, onSessionUpdate, onCommitPending, loading, streaming]
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
            {sessionMetrics?.latest_run?.status && sessionMetrics.latest_run.status !== 'completed' && (
              <span className="ml-2 text-amber-700">{sessionMetrics.latest_run.status === 'running' ? '执行中（已保存检查点）' : sessionMetrics.latest_run.status}</span>
            )}
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
