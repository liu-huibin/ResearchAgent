import { useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/TextLayer.css';
import 'react-pdf/dist/Page/AnnotationLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface PDFViewerProps {
  fileUrl: string;
}

export default function PDFViewer({ fileUrl }: PDFViewerProps) {
  const [numPages, setNumPages] = useState(0);
  const [scale, setScale] = useState(1.2);
  const [loadError, setLoadError] = useState(false);

  return (
    <div className="flex flex-col items-center p-2">
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
        file={fileUrl}
        onLoadSuccess={({ numPages }) => setNumPages(numPages)}
        onLoadError={() => setLoadError(true)}
        loading={<div className="text-gray-400 text-sm p-4">加载 PDF 中...</div>}
        error={<div className="text-red-400 text-sm p-4">{loadError ? '找不到该文档，可能被删除' : 'PDF 加载失败'}</div>}
      >
        {Array.from({ length: numPages }, (_, i) => (
          <div key={`page_${i + 1}`} className="mb-3 shadow-md">
            <Page
              pageNumber={i + 1}
              scale={scale}
              renderTextLayer={true}
              renderAnnotationLayer={true}
            />
          </div>
        ))}
      </Document>
    </div>
  );
}
