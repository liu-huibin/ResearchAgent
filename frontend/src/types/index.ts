export interface Session {
  id: number;
  title: string;
  active_document_id: number | null;
  updated_at: string;
}

export interface Message {
  id: number;
  session_id: number;
  role: 'user' | 'assistant' | 'tool';
  content: string | null;
  tool_calls: ToolCall[] | null;
  created_at: string;
}

export interface ToolCall {
  kind?: 'stage' | 'tool';
  agent?: AgentName;
  stage?: string;
  detail?: string;
  report?: string;
  tool?: string;
  status: 'running' | 'succeeded' | 'failed';
  is_error?: boolean;
}

export type AgentName = 'Supervisor' | 'ReaderAgent' | 'IdeationAgent' | 'ReviewerAgent';

export interface Document {
  id: number;
  filename: string;
  type: 'session' | 'knowledge';
  session_id: number | null;
  created_at: string;
}

export interface SSEMessageEvent {
  type: 'start' | 'agent' | 'report' | 'action' | 'observation' | 'token' | 'metrics' | 'done' | 'error';
  persisted?: boolean;
  content?: string;
  agent?: AgentName;
  stage?: string;
  detail?: string;
  tool?: string;
  is_error?: boolean;
  message_id?: number;
  trace_id?: string;
  status?: string;
  prompt_variant?: string;
  prompt_version?: string;
  langsmith_enabled?: boolean;
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  agent_usage?: Record<string, AgentUsage>;
  iterations?: number;
  tool_calls?: number;
  tool_failures?: number;
  duration_ms?: number;
}

export interface AgentUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  llm_calls_failed: number;
  llm_latency_ms: number;
  models: string[];
}

export interface WorkflowRunMetrics {
  id: number;
  session_id: number;
  assistant_message_id: number | null;
  trace_id: string;
  status: string;
  prompt_variant: string;
  prompt_version: string;
  langsmith_enabled: boolean;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  agent_usage: Record<string, AgentUsage> | null;
  iterations: number;
  tool_calls: number;
  tool_failures: number;
  duration_ms: number;
  started_at: string;
  completed_at: string;
}

export interface SessionMetrics {
  session_id: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  run_count: number;
  latest_run: WorkflowRunMetrics | null;
  runs: WorkflowRunMetrics[];
}

export interface DocumentTab {
  id: string;
  documentId: number;
  filename: string;
  fileUrl: string;
  isPdf: boolean;
  label: string;
  citation?: CitationLocation;
  navigationKey?: number;
}

export interface CitationFragment {
  unit: number;
  unit_text: string;
  start: number;
  end: number;
  text: string;
  occurrence: number;
}

export interface CitationLocation {
  document_id: number;
  chunk_index: number;
  filename: string;
  file_type: 'pdf' | 'docx';
  text: string;
  status: 'exact' | 'ambiguous' | 'unavailable';
  fragments: CitationFragment[];
}
