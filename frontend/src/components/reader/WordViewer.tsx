import { useState, useEffect } from 'react';
import mammoth from 'mammoth';

interface WordViewerProps {
  fileUrl: string;
}

export default function WordViewer({ fileUrl }: WordViewerProps) {
  const [html, setHtml] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    fetch(fileUrl)
      .then((res) => res.arrayBuffer())
      .then((buffer) =>
        mammoth.convertToHtml({ arrayBuffer: buffer })
      )
      .then((result) => {
        setHtml(result.value);
        setLoading(false);
      })
      .catch(() => {
        setError('Word 文档加载失败');
        setLoading(false);
      });
  }, [fileUrl]);

  if (loading) {
    return <div className="text-gray-400 text-sm p-4 text-center">加载 Word 文档中...</div>;
  }

  if (error) {
    return <div className="text-red-400 text-sm p-4 text-center">{error}</div>;
  }

  return (
    <div
      className="p-6 max-w-3xl mx-auto bg-white min-h-full"
      dangerouslySetInnerHTML={{ __html: html }}
      style={{
        fontFamily: 'Georgia, serif',
        lineHeight: 1.8,
      }}
    />
  );
}
