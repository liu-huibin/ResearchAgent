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
  thought: string | null;
  tool_calls: ToolCall[] | null;
  created_at: string;
}

export interface ToolCall {
  tool: string;
  input: string | Record<string, unknown>;
  output?: string;
}

export interface Document {
  id: number;
  filename: string;
  type: 'session' | 'knowledge';
  session_id: number | null;
  created_at: string;
}

export interface SSEMessageEvent {
  type: 'thought' | 'action' | 'observation' | 'token' | 'done' | 'error';
  content?: string;
  tool?: string;
  input?: string;
  output?: string;
  message_id?: number;
}
