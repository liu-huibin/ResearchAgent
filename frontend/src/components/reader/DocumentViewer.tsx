import { useState, useEffect } from 'react';
import PDFViewer from './PDFViewer';
import WordViewer from './WordViewer';
import TabBar from './TabBar';
import { api } from '../../services/api';
import { useDocumentTabs } from '../../contexts/DocumentTabsContext';
import type { Session } from '../../types';

interface DocumentViewerProps {
  sessionId: number | null;
  onCommitPending?: (tempId: number) => Promise<Session | undefined>;
}

export default function DocumentViewer({ sessionId, onCommitPending }: DocumentViewerProps) {
  const { tabs, activeTabId, openTab, closeTab, setActiveTab, closeAllTabs } = useDocumentTabs();
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Auto-open session document as tab when session changes; close all previous tabs
  useEffect(() => {
    let stale = false;
    if (!sessionId) {
      closeAllTabs();
      return;
    }
    closeAllTabs();
    setLoading(true);
    api.getSessionDocument(sessionId)
      .then((doc) => {
        if (stale) return;
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
      .catch(() => undefined)
      .finally(() => { if (!stale) setLoading(false); });
    return () => { stale = true; };
  }, [sessionId, closeAllTabs, openTab]);

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
      const ext = uploaded.filename.split('.').pop()?.toLowerCase();
      openTab({
        documentId: uploaded.id,
        filename: uploaded.filename,
        fileUrl: api.getDocumentFileUrl(uploaded.id),
        isPdf: ext === 'pdf',
        label: uploaded.filename.length > 20 ? uploaded.filename.slice(0, 20) + '...' : uploaded.filename,
      });
    } catch {
      alert('上传失败');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  // Find active tab
  const activeTab = tabs.find((t) => t.id === activeTabId);
  const viewerKey = activeTab
    ? `${activeTab.id}:${activeTab.navigationKey ?? 0}`
    : undefined;

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
      {activeTab?.citation && (
        <div role="status" className="p-2 text-xs bg-amber-50 border-b border-amber-200">
          引用分块 {activeTab.citation.chunk_index + 1} · {activeTab.citation.status === 'exact'
            ? `${activeTab.isPdf ? '页码' : '段落'} ${activeTab.citation.fragments.map(f => f.unit).join('、')}`
            : activeTab.citation.status === 'ambiguous' ? '存在重复文本，无法唯一定位' : '原文未匹配，无法定位'}
          <details><summary>查看引用原文</summary><p className="whitespace-pre-wrap">{activeTab.citation.text}</p></details>
        </div>
      )}

      {/* Content area */}
      <div className="flex-1 overflow-auto">
        {activeTab ? (
          activeTab.isPdf ? (
            <PDFViewer key={viewerKey} fileUrl={activeTab.fileUrl} citation={activeTab.citation} />
          ) : (
            <WordViewer key={viewerKey} fileUrl={activeTab.fileUrl} citation={activeTab.citation} />
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
                {uploading ? '上传中...' : '上传 PDF / DOCX'}
                <input
                  type="file"
                  accept=".pdf,.docx"
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
