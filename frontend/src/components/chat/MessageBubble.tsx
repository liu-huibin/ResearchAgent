import { useState } from 'react';
import ThoughtProcess from './ThoughtProcess';
import type { Message } from '../../types';

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
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
            {message.content}
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
