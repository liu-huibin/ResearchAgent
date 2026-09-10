import { useState } from 'react';
import MarkdownRenderer from './MarkdownRenderer';
import type { AgentName, ToolCall } from '../../types';

interface ThoughtProcessProps {
  toolCalls: ToolCall[];
  activeAgent?: AgentName | null;
  onCitationClick?: (docId: number, chunkIndex: number) => void | Promise<void>;
}

const agentLabels: Record<AgentName, string> = {
  Supervisor: '协调',
  ReaderAgent: '论文阅读',
  IdeationAgent: '思路生成',
  ReviewerAgent: '内容审查',
};

const stageLabels: Record<string, string> = {
  supervisor: '分析任务并选择协作路线',
  reader: '阅读材料并提取相关证据',
  ideation: '根据证据形成候选研究思路',
  reviewer: '核查事实、创新性与可行性',
  revision: '根据审查意见修正候选内容',
  finalize: '汇总并生成可公开回答',
  unknown: '处理当前任务',
};

const statusLabel = (status: ToolCall['status']) =>
  status === 'running' ? '进行中' : status === 'failed' ? '失败' : '完成';

export default function ThoughtProcess({ toolCalls, activeAgent, onCitationClick }: ThoughtProcessProps) {
  const [collapsed, setCollapsed] = useState(false);

  const hasContent = Boolean(activeAgent) || toolCalls.length > 0;
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
        <span>推理与协作说明</span>
        {activeAgent && (
          <span className="ml-1 rounded-full bg-blue-50 px-2 py-0.5 text-blue-600">
            {activeAgent} · {agentLabels[activeAgent]}
          </span>
        )}
      </button>

      {!collapsed && (
        <div className="mt-1 p-3 bg-gray-50 rounded border border-gray-200 text-gray-500 whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto">
          <div className="mb-2 text-[11px] text-gray-400">
            展示任务判断、依据、关键取舍和下一步；不包含模型隐藏思维链、提示词或工具原始数据。
          </div>
          {toolCalls.map((item, i) => {
            const isStage = item.kind === 'stage';
            const failed = item.status === 'failed' || item.is_error;
            return (
              <div key={i} className={`mt-2 p-2 bg-white rounded border ${failed ? 'border-red-200' : 'border-gray-100'}`}>
                <div className={`font-medium ${failed ? 'text-red-600' : 'text-gray-600'}`}>
                  {isStage ? '●' : '🔧'}{' '}
                  {item.agent ? `${agentLabels[item.agent]} · ` : ''}
                  {isStage ? (stageLabels[item.stage || 'unknown'] || stageLabels.unknown) : (item.tool || '未命名工具')}
                </div>
                {isStage && item.detail && (
                  <div className="mt-1.5 text-gray-500 leading-relaxed">
                    {item.detail}
                  </div>
                )}
                {isStage && item.report && (
                  <div className="mt-2 rounded border border-blue-100 bg-blue-50/60 p-2 text-gray-600 leading-relaxed">
                    <div className="mb-1 font-medium text-blue-700">Agent 公开报告</div>
                    <MarkdownRenderer content={item.report} onCitationClick={onCitationClick} />
                  </div>
                )}
                <div className="mt-1 text-gray-400">状态：{statusLabel(item.status)}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
