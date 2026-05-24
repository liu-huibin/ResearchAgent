import { useState } from 'react';

interface ThoughtProcessProps {
  thought: string;
  toolCalls: { tool: string; input: string; output?: string }[];
}

export default function ThoughtProcess({ thought, toolCalls }: ThoughtProcessProps) {
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
        <span>思考过程</span>
      </button>

      {!collapsed && (
        <div className="mt-1 p-3 bg-gray-50 rounded border border-gray-200 text-gray-500 whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto">
          {thought && <div>{thought}</div>}
          {toolCalls.map((tc, i) => (
            <div key={i} className="mt-2 p-2 bg-white rounded border border-gray-100">
              <div className="font-medium text-gray-600">🔧 {tc.tool}</div>
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
