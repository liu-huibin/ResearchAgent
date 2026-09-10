import { useState, useEffect, useRef } from 'react';
import type { CitationLocation } from '../../types';
import { clearCitationMarks, highlightCitation, normalizeCitationText } from './citationHighlight';
import mammoth from 'mammoth';
import { authorizedFetch } from '../../services/security';

interface WordViewerProps {
  fileUrl: string;
  citation?: CitationLocation;
}

function sanitizeDocumentHtml(value: string): string {
  const parsed = new DOMParser().parseFromString(value, 'text/html');
  parsed.querySelectorAll('script,style,iframe,object,embed,form,base,meta,link').forEach(
    (element) => element.remove(),
  );
  parsed.querySelectorAll('*').forEach((element) => {
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      const content = attribute.value.trim().toLowerCase();
      if (name.startsWith('on') || name === 'style') {
        element.removeAttribute(attribute.name);
      } else if ((name === 'href' || name === 'src') && /^(javascript|vbscript):/.test(content)) {
        element.removeAttribute(attribute.name);
      } else if (name === 'src' && content.startsWith('data:') && !content.startsWith('data:image/')) {
        element.removeAttribute(attribute.name);
      }
    }
  });
  return parsed.body.innerHTML;
}

export default function WordViewer({ fileUrl, citation }: WordViewerProps) {
  const root = useRef<HTMLDivElement>(null);
  const [locationError, setLocationError] = useState('');
  const [html, setHtml] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let stale = false;
    const controller = new AbortController();
    setLoading(true);
    setError('');
    authorizedFetch(fileUrl, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) {
          throw new Error(res.status === 404 ? 'NOT_FOUND' : 'LOAD_ERROR');
        }
        return res.arrayBuffer();
      })
      .then((buffer) =>
        mammoth.convertToHtml({ arrayBuffer: buffer })
      )
      .then((result) => {
        if (stale) return;
        setHtml(sanitizeDocumentHtml(result.value));
        setLoading(false);
      })
      .catch((err) => {
        if (stale) return;
        setError(err.message === 'NOT_FOUND' ? '找不到该文档，可能被删除' : 'Word 文档加载失败');
        setLoading(false);
      });
    return () => { stale = true; controller.abort(); };
  }, [fileUrl]);

  useEffect(() => {
    if (!root.current || loading) return;
    clearCitationMarks(root.current);
    setLocationError('');
    const elements = Array.from(root.current.querySelectorAll<HTMLElement>('p,h1,h2,h3,h4,h5,h6,li'))
      .filter(element => !element.closest('table') && !element.querySelector('p,li'));
    let first: HTMLElement | null = null;
    for (const fragment of citation?.fragments ?? []) {
      const matches = elements.filter(el => normalizeCitationText(el.textContent ?? '') === normalizeCitationText(fragment.unit_text));
      const element = matches[fragment.occurrence];
      const mark = element ? highlightCitation(element, fragment) : null;
      first ??= mark ?? element;
      if (!mark) setLocationError('Word 渲染段落与原文不一致，部分引用未能精确高亮。');
    }
    first?.scrollIntoView({ block: 'center' });
  }, [citation, html, loading]);

  if (loading) {
    return <div className="text-gray-400 text-sm p-4 text-center">加载 Word 文档中...</div>;
  }

  if (error) {
    return <div className="text-red-400 text-sm p-4 text-center">{error}</div>;
  }

  return (
    <>
    {locationError && <p role="status" className="text-amber-700 text-sm p-2">{locationError}</p>}
    <div ref={root}
      className="p-6 max-w-3xl mx-auto bg-white min-h-full"
      dangerouslySetInnerHTML={{ __html: html }}
      style={{
        fontFamily: 'Georgia, serif',
        lineHeight: 1.8,
      }}
    />
    </>
  );
}
