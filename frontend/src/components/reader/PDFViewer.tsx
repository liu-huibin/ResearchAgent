import { useMemo, useState, useRef, useEffect, useCallback } from 'react';
import type { CitationLocation } from '../../types';
import { clearCitationMarks, highlightCitation } from './citationHighlight';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/TextLayer.css';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import { apiHeaders } from '../../services/security';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

interface PDFViewerProps {
  fileUrl: string;
  citation?: CitationLocation;
}

export default function PDFViewer({ fileUrl, citation }: PDFViewerProps) {
  const root = useRef<HTMLDivElement>(null);
  const [locationError, setLocationError] = useState('');
  const locate = useCallback((page?: number) => {
    if (!root.current) return;
    for (const fragment of citation?.fragments ?? []) {
      if (page !== undefined && page !== fragment.unit) continue;
      const pageRoot = root.current.querySelector<HTMLElement>(`[data-page="${fragment.unit}"]`);
      const layer = pageRoot?.querySelector<HTMLElement>('.react-pdf__Page__textContent');
      if (!layer) continue;
      clearCitationMarks(layer);
      const mark = highlightCitation(layer, fragment);
      if (!mark) setLocationError('已定位页码，但 PDF 文本层与提取文本不一致，无法精确高亮。');
      if (fragment === citation?.fragments[0]) (mark ?? pageRoot)?.scrollIntoView({ block: 'center' });
    }
  }, [citation]);
  useEffect(() => {
    if (root.current) clearCitationMarks(root.current);
    setLocationError('');
    locate();
  }, [locate]);
  const [numPages, setNumPages] = useState(0);
  const [scale, setScale] = useState(1.2);
  const [loadError, setLoadError] = useState(false);
  const file = useMemo(
    () => ({ url: fileUrl, httpHeaders: Object.fromEntries(apiHeaders()) }),
    [fileUrl],
  );

  return (
    <div ref={root} className="flex flex-col items-center p-2">
      {locationError && <p role="status" className="text-amber-700 text-sm">{locationError}</p>}
      {/* Zoom controls */}
      <div className="flex items-center gap-3 mb-3 bg-white rounded-lg px-3 py-1.5 shadow-sm sticky top-0 z-10">
        <button
          onClick={() => setScale((s) => Math.max(0.5, s - 0.2))}
          className="px-2 py-0.5 text-sm rounded hover:bg-gray-100"
        >
          −
        </button>
        <span className="text-sm text-gray-500 w-12 text-center">{Math.round(scale * 100)}%</span>
        <button
          onClick={() => setScale((s) => Math.min(2.5, s + 0.2))}
          className="px-2 py-0.5 text-sm rounded hover:bg-gray-100"
        >
          +
        </button>
        <span className="text-sm text-gray-400 ml-2">
          {numPages > 0 ? `共 ${numPages} 页` : ''}
        </span>
      </div>

      <Document
        file={file}
        onLoadSuccess={({ numPages }) => setNumPages(numPages)}
        onLoadError={() => setLoadError(true)}
        loading={<div className="text-gray-400 text-sm p-4">加载 PDF 中...</div>}
        error={<div className="text-red-400 text-sm p-4">{loadError ? '找不到该文档，可能被删除' : 'PDF 加载失败'}</div>}
      >
        {Array.from({ length: numPages }, (_, i) => (
          <div key={`page_${i + 1}`} data-page={i + 1} className="mb-3 shadow-md">
            <Page
              pageNumber={i + 1}
              scale={scale}
              renderTextLayer={true}
              renderAnnotationLayer={true}
              onRenderTextLayerSuccess={() => locate(i + 1)}
            />
          </div>
        ))}
      </Document>
    </div>
  );
}
