import { useState } from 'react';
import { api } from '../../services/api';
import { useDocumentTabs } from '../../contexts/DocumentTabsContext';
import type { Document } from '../../types';

interface KnowledgeItemProps {
  document: Document;
  uploadProgress?: number;
  onDelete: () => void;
}

export default function KnowledgeItem({ document: doc, uploadProgress, onDelete }: KnowledgeItemProps) {
  const [showConfirm, setShowConfirm] = useState(false);
  const { openTab } = useDocumentTabs();

  const ext = doc.filename.split('.').pop()?.toLowerCase();
  const isPdf = ext === 'pdf';

  const handleOpen = () => {
    openTab({
      documentId: doc.id,
      filename: doc.filename,
      fileUrl: api.getDocumentFileUrl(doc.id),
      isPdf: ext === 'pdf',
      label: doc.filename.length > 20 ? doc.filename.slice(0, 20) + '...' : doc.filename,
    });
  };

  return (
    <>
      <div className="group flex items-center gap-2 px-3 py-2 hover:bg-gray-50 text-sm">
        <span className="text-base flex-shrink-0">
          {isPdf ? '📄' : '📃'}
        </span>
        <button
          onClick={handleOpen}
          className="flex-1 text-left text-gray-700 truncate text-xs hover:text-blue-600"
          title={doc.filename}
        >
          {doc.filename}
        </button>
        {uploadProgress !== undefined && uploadProgress < 100 ? (
          <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden flex-shrink-0">
            <div
              className="h-full bg-blue-500 rounded-full transition-all duration-300"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        ) : (
          <button
            onClick={() => setShowConfirm(true)}
            className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600 text-xs flex-shrink-0 transition-opacity"
            title="删除"
          >
            ✕
          </button>
        )}
      </div>

      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="bg-white rounded-lg p-4 shadow-xl mx-4 max-w-xs w-full">
            <p className="text-sm text-gray-700 mb-3">
              确定要从知识库中删除 "{doc.filename}" 吗？此操作不可恢复。
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowConfirm(false)}
                className="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700"
              >
                取消
              </button>
              <button
                onClick={() => { onDelete(); setShowConfirm(false); }}
                className="px-3 py-1.5 text-xs bg-red-500 text-white rounded hover:bg-red-600"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
