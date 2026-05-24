import { useState, useEffect } from 'react';
import PDFViewer from './PDFViewer';
import WordViewer from './WordViewer';
import { api } from '../../services/api';
import type { Document, Session } from '../../types';

interface DocumentViewerProps {
  sessionId: number | null;
  onCommitPending?: (tempId: number) => Promise<Session | undefined>;
}

export default function DocumentViewer({ sessionId, onCommitPending }: DocumentViewerProps) {
  const [doc, setDoc] = useState<Document | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (!sessionId) {
      setDoc(null);
      return;
    }
    setLoading(true);
    api.getSessionDocument(sessionId)
      .then(setDoc)
      .catch(() => setDoc(null))
      .finally(() => setLoading(false));
  }, [sessionId]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !sessionId) return;
    setUploading(true);
    try {
      let realSessionId = sessionId;
      // Commit pending session before upload
      if (sessionId < 0 && onCommitPending) {
        const real = await onCommitPending(sessionId);
        if (!real) {
          alert('创建会话失败');
          return;
        }
        realSessionId = real.id;
      }
      const uploaded = await api.uploadDocument(realSessionId, file);
      setDoc(uploaded);
    } catch (err) {
      alert('上传失败');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  if (!sessionId) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        请选择或创建一个会话
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        加载中...
      </div>
    );
  }

  if (!doc) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
        <span>暂无文档，请上传文件到当前会话</span>
        <label className="px-4 py-2 bg-blue-600 text-white rounded-lg cursor-pointer hover:bg-blue-700 transition-colors text-sm">
          {uploading ? '上传中...' : '上传 PDF / Word'}
          <input
            type="file"
            accept=".pdf,.doc,.docx"
            className="hidden"
            onChange={handleUpload}
            disabled={uploading}
          />
        </label>
      </div>
    );
  }

  const fileUrl = api.getDocumentFileUrl(doc.id);
  const isPDF = doc.filename.toLowerCase().endsWith('.pdf');

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-white border-b border-gray-200 shrink-0">
        <span className="text-sm font-medium text-gray-700 truncate">{doc.filename}</span>
        <label className="px-2 py-1 text-xs text-blue-600 cursor-pointer hover:bg-blue-50 rounded transition-colors">
          更换文档
          <input
            type="file"
            accept=".pdf,.doc,.docx"
            className="hidden"
            onChange={handleUpload}
            disabled={uploading}
          />
        </label>
      </div>
      {/* Content */}
      <div className="flex-1 overflow-auto">
        {isPDF ? <PDFViewer fileUrl={fileUrl} /> : <WordViewer fileUrl={fileUrl} />}
      </div>
    </div>
  );
}
