import { useState, type ReactNode } from 'react';
import ThoughtProcess from './ThoughtProcess';
import { api } from '../../services/api';
import type { Message } from '../../types';

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

const CITATION_RE = /\[citation:doc_(\d+):chunk_(\d+)\]/g;

function renderContent(content: string): ReactNode {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  const regex = new RegExp(CITATION_RE.source, 'g');
  while ((match = regex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push(content.slice(lastIndex, match.index));
    }
    const docId = parseInt(match[1], 10);
    parts.push(
      <span
        key={`citation-${match.index}`}
        className="inline-flex items-center px-1.5 py-0.5 mx-0.5 text-xs bg-blue-100 text-blue-700 rounded cursor-pointer hover:bg-blue-200 align-bottom"
        onClick={() => window.open(api.getDocumentFileUrl(docId), '_blank')}
        title={`查看来源文档`}
      >
        来源
      </span>
    );
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex));
  }

  return parts.length > 0 ? parts : content;
}

export default function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);

  const isUser = message.role === 'user';

  const handleCopy = () => {
    if (message.content) {
      navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] px-4 py-2 bg-blue-600 text-white rounded-2xl rounded-br-md text-sm leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      {/* Thought process */}
      {(message.thought || (isStreaming && message.tool_calls?.length)) && (
        <ThoughtProcess
          thought={message.thought || ''}
          toolCalls={(message.tool_calls || []).map(tc => ({ ...tc, input: typeof tc.input === 'string' ? tc.input : JSON.stringify(tc.input) }))}
        />
      )}

      {/* Main content */}
      {message.content && (
        <div className="p-3 bg-gray-50 rounded-lg border border-gray-100 group">
          <div className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
            {renderContent(message.content)}
            {isStreaming && (
              <span className="inline-block w-2 h-4 bg-gray-600 animate-pulse ml-0.5 align-middle" />
            )}
          </div>
          {!isStreaming && message.content && (
            <div className="flex items-center gap-2 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={handleCopy}
                className="text-xs text-gray-400 hover:text-gray-600"
              >
                {copied ? '已复制' : '复制'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
