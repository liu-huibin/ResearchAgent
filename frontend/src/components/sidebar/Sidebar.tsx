import SessionList from './SessionList';
import KnowledgeBase from './KnowledgeBase';
import type { Session, Document } from '../../types';

interface UploadItem {
  filename: string;
  progress: number;
}

interface SidebarProps {
  sessions: Session[];
  activeId: number | null;
  loading: boolean;
  onSelect: (id: number) => void;
  onCreate: () => void;
  onDelete: (id: number) => void;
  onRename: (id: number, title: string) => void;
  knowledgeDocs: Document[];
  knowledgeUploads: UploadItem[];
  knowledgeLoading: boolean;
  onKnowledgeUpload: (file: File) => void;
  onKnowledgeDelete: (docId: number) => void;
}

export default function Sidebar({
  sessions, activeId, loading,
  onSelect, onCreate, onDelete, onRename,
  knowledgeDocs, knowledgeUploads, knowledgeLoading,
  onKnowledgeUpload, onKnowledgeDelete,
}: SidebarProps) {
  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-gray-200">
        <button
          onClick={onCreate}
          className="w-full py-2 px-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          + 新建会话
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-center text-gray-400 text-sm">加载中...</div>
        ) : sessions.length === 0 ? (
          <div className="p-4 text-center text-gray-400 text-sm">暂无会话</div>
        ) : (
          <SessionList
            sessions={sessions}
            activeId={activeId}
            onSelect={onSelect}
            onDelete={onDelete}
            onRename={onRename}
          />
        )}
      </div>
      <KnowledgeBase
        documents={knowledgeDocs}
        uploads={knowledgeUploads}
        loading={knowledgeLoading}
        onUpload={onKnowledgeUpload}
        onDelete={onKnowledgeDelete}
      />
    </div>
  );
}
