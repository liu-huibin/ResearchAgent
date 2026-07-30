import { useState } from 'react';
import type { AgentName } from '../../types';

interface ThoughtProcessProps {
  thought: string;
  toolCalls: { agent?: AgentName; tool: string; input: string; output?: string; is_error?: boolean }[];
  activeAgent?: AgentName | null;
}

const agentLabels: Record<AgentName, string> = {
  Supervisor: '协调',
  ReaderAgent: '论文阅读',
  IdeationAgent: '思路生成',
  ReviewerAgent: '内容审查',
};

export default function ThoughtProcess({ thought, toolCalls, activeAgent }: ThoughtProcessProps) {
  const [collapsed, setCollapsed] = useState(false);

  const hasContent = thought.trim() || toolCalls.length > 0;
  if (!hasContent) return null;

  return (
    <div className="text-xs">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center gap-1 text-gray-400 hover:text-gray-600 transition-colors"
      >
        <span className="transform transition-transform" style={{ rotate: collapsed ? '0deg' : '90deg' }}>
          ▶
        </span>
        <span>协作过程</span>
        {activeAgent && (
          <span className="ml-1 rounded-full bg-blue-50 px-2 py-0.5 text-blue-600">
            {activeAgent} · {agentLabels[activeAgent]}
          </span>
        )}
      </button>

      {!collapsed && (
        <div className="mt-1 p-3 bg-gray-50 rounded border border-gray-200 text-gray-500 whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto">
          {thought && <div>{thought}</div>}
          {toolCalls.map((tc, i) => (
            <div key={i} className={`mt-2 p-2 bg-white rounded border ${tc.is_error ? 'border-red-200' : 'border-gray-100'}`}>
              <div className={`font-medium ${tc.is_error ? 'text-red-600' : 'text-gray-600'}`}>
                🔧 {tc.agent ? `${tc.agent} · ` : ''}{tc.tool}
              </div>
              <div className="mt-1 text-gray-400">输入: {typeof tc.input === 'string' ? tc.input : JSON.stringify(tc.input)}</div>
              {tc.output && (
                <div className="mt-1 text-gray-400 truncate">输出: {tc.output}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
