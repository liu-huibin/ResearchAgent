import { useState, useRef } from 'react';
import KnowledgeItem from './KnowledgeItem';
import type { Document } from '../../types';

interface UploadItem {
  id: string;
  filename: string;
  progress: number;
}

interface KnowledgeBaseProps {
  documents: Document[];
  uploads: UploadItem[];
  loading: boolean;
  onUpload: (file: File) => void;
  onDelete: (docId: number) => void;
}

export default function KnowledgeBase({
  documents, uploads, loading, onUpload, onDelete,
}: KnowledgeBaseProps) {
  const [collapsed, setCollapsed] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (!['pdf', 'doc', 'docx'].includes(ext || '')) {
      alert('仅支持 PDF/Word 文件');
      // reset input value
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }
    onUpload(file);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="border-t border-gray-200">
      <div className="flex items-center justify-between px-3 py-2">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center gap-1 text-xs font-medium text-gray-500 hover:text-gray-700"
        >
          <span className={`transition-transform ${collapsed ? '' : 'rotate-90'}`}>▶</span>
          知识库
        </button>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="text-xs text-blue-600 hover:text-blue-700 font-medium"
        >
          + 上传
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.doc,.docx"
          onChange={handleFileChange}
          className="hidden"
        />
      </div>

      {!collapsed && (
        <div className="max-h-[200px] overflow-y-auto border-t border-gray-100">
          {loading ? (
            <div className="p-3 text-center text-gray-400 text-xs">加载中...</div>
          ) : uploads.length === 0 && documents.length === 0 ? (
            <div className="p-3 text-center text-gray-400 text-xs">暂无知识库文档</div>
          ) : (
            <>
              {uploads.map((u) => (
                <div key={u.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                  <span className="text-base">📄</span>
                  <span className="flex-1 text-xs text-gray-500 truncate">{u.filename}</span>
                  <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden flex-shrink-0">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all"
                      style={{ width: `${u.progress}%` }}
                    />
                  </div>
                </div>
              ))}
              {documents.map(doc => (
                <KnowledgeItem
                  key={doc.id}
                  document={doc}
                  onDelete={() => onDelete(doc.id)}
                />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
