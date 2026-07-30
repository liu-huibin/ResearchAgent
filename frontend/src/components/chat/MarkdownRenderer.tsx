import { Fragment } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '../../services/api';

const CITATION_RE = /\[citation:doc_(\d+):chunk_(\d+)\]/g;

function CitationBadge({ docId, onClick }: { docId: number; onClick: (docId: number) => void }) {
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 mx-0.5 text-xs bg-blue-100 text-blue-700 rounded cursor-pointer hover:bg-blue-200 align-bottom"
      onClick={(e) => { e.stopPropagation(); onClick(docId); }}
      title="查看来源文档"
    >
      来源
    </span>
  );
}

interface MarkdownRendererProps {
  content: string;
  onCitationClick?: (docId: number) => void;
}

export default function MarkdownRenderer({ content, onCitationClick }: MarkdownRendererProps) {
  const handleCitation = (docId: number) => {
    if (onCitationClick) {
      onCitationClick(docId);
    } else {
      window.open(api.getDocumentFileUrl(docId), '_blank');
    }
  };

  // Split content by citation markers, render each text segment as markdown,
  // and insert citation badges between segments.
  const segments: { type: 'text' | 'citation'; value: string; docId?: number }[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  const regex = new RegExp(CITATION_RE.source, 'g');
  while ((match = regex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', value: content.slice(lastIndex, match.index) });
    }
    segments.push({ type: 'citation', value: match[0], docId: parseInt(match[1], 10) });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < content.length) {
    segments.push({ type: 'text', value: content.slice(lastIndex) });
  }

  // If no citations found, just render markdown
  if (segments.length === 0) {
    segments.push({ type: 'text', value: content });
  }

  // Strip trailing newlines from text segments that precede a citation,
  // so the citation badge flows inline after the text (e.g. after "。")
  // instead of appearing on its own line.
  for (let i = 0; i < segments.length - 1; i++) {
    if (segments[i].type === 'text' && segments[i + 1].type === 'citation') {
      segments[i].value = segments[i].value.replace(/\n+$/, '');
    }
  }

  const proseClasses =
    'prose prose-sm max-w-none ' +
    'prose-headings:text-gray-800 prose-p:text-gray-700 prose-p:my-1 ' +
    'prose-a:text-blue-600 ' +
    'prose-code:text-pink-600 prose-code:bg-gray-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none ' +
    'prose-pre:bg-gray-900 prose-pre:text-gray-100 ' +
    'prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 ' +
    'prose-table:border-collapse prose-th:border prose-th:border-gray-300 prose-th:px-2 prose-th:py-1 prose-td:border prose-td:border-gray-300 prose-td:px-2 prose-td:py-1 ' +
    'prose-img:rounded-lg';

  const renderText = (text: string) => (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children, ...props }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>
        ),
        p: ({ children, ...props }) => (
          <p className="my-1.5" {...props}>{children}</p>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  );

  return (
    <div className={proseClasses}>
      {segments.map((seg, i) =>
        seg.type === 'citation' ? (
          <CitationBadge key={`cite-${i}`} docId={seg.docId!} onClick={handleCitation} />
        ) : (
          <Fragment key={`text-${i}`}>{renderText(seg.value)}</Fragment>
        )
      )}
    </div>
  );
}
