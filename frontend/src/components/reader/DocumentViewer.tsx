import { useState, useEffect } from 'react';
import PDFViewer from './PDFViewer';
import WordViewer from './WordViewer';
import TabBar from './TabBar';
import { api } from '../../services/api';
import { useDocumentTabs } from '../../contexts/DocumentTabsContext';
import type { Document, Session } from '../../types';

interface DocumentViewerProps {
  sessionId: number | null;
  onCommitPending?: (tempId: number) => Promise<Session | undefined>;
}

export default function DocumentViewer({ sessionId, onCommitPending }: DocumentViewerProps) {
  const { tabs, activeTabId, openTab, closeTab, setActiveTab, closeAllTabs } = useDocumentTabs();
  const [sessionDoc, setSessionDoc] = useState<Document | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Auto-open session document as tab when session changes; close all previous tabs
  useEffect(() => {
    if (!sessionId) {
      setSessionDoc(null);
      closeAllTabs();
      return;
    }
    closeAllTabs();
    setLoading(true);
    api.getSessionDocument(sessionId)
      .then((doc) => {
        setSessionDoc(doc);
        if (doc) {
          const ext = doc.filename.split('.').pop()?.toLowerCase();
          openTab({
            id: `doc_${doc.id}`,
            documentId: doc.id,
            filename: doc.filename,
            fileUrl: api.getDocumentFileUrl(doc.id),
            isPdf: ext === 'pdf',
            label: doc.filename.length > 20 ? doc.filename.slice(0, 20) + '...' : doc.filename,
          });
        }
      })
      .catch(() => setSessionDoc(null))
      .finally(() => setLoading(false));
  }, [sessionId]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !sessionId) return;
    setUploading(true);
    try {
      let realSessionId = sessionId;
      if (sessionId < 0 && onCommitPending) {
        const real = await onCommitPending(sessionId);
        if (!real) {
          alert('创建会话失败');
          return;
        }
        realSessionId = real.id;
      }
      const uploaded = await api.uploadDocument(realSessionId, file);
      setSessionDoc(uploaded);
      const ext = uploaded.filename.split('.').pop()?.toLowerCase();
      openTab({
        documentId: uploaded.id,
        filename: uploaded.filename,
        fileUrl: api.getDocumentFileUrl(uploaded.id),
        isPdf: ext === 'pdf',
        label: uploaded.filename.length > 20 ? uploaded.filename.slice(0, 20) + '...' : uploaded.filename,
      });
    } catch (err) {
      alert('上传失败');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  // Find active tab
  const activeTab = tabs.find((t) => t.id === activeTabId);

  // No tabs open
  if (!sessionId && tabs.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        请选择或创建一个会话
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <TabBar tabs={tabs} activeTabId={activeTabId} onSelect={setActiveTab} onClose={closeTab} />

      {/* Content area */}
      <div className="flex-1 overflow-auto">
        {activeTab ? (
          activeTab.isPdf ? (
            <PDFViewer fileUrl={activeTab.fileUrl} />
          ) : (
            <WordViewer fileUrl={activeTab.fileUrl} />
          )
        ) : tabs.length === 0 && sessionId ? (
          loading ? (
            <div className="flex items-center justify-center h-full text-gray-400">
              加载中...
            </div>
          ) : (
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
          )
        ) : tabs.length === 0 ? null : (
          <div className="flex items-center justify-center h-full text-gray-400">
            选择或关闭标签页
          </div>
        )}
      </div>
    </div>
  );
}
