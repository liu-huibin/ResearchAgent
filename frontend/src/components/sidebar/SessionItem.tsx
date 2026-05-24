import { useState, useRef, useEffect } from 'react';
import type { Session } from '../../types';

interface SessionItemProps {
  session: Session;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onRename: (title: string) => void;
}

export default function SessionItem({
  session, isActive, onSelect, onDelete, onRename,
}: SessionItemProps) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(session.title);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const handleRename = () => {
    const trimmed = title.trim();
    if (trimmed && trimmed.length <= 50) {
      onRename(trimmed);
    } else {
      setTitle(session.title);
    }
    setEditing(false);
  };

  const handleDeleteConfirm = () => {
    onDelete();
    setShowDeleteModal(false);
  };

  return (
    <>
      <div
        className={`group flex items-center px-3 py-2 cursor-pointer mx-1 rounded-lg transition-colors ${
          isActive
            ? 'bg-blue-50 text-blue-700'
            : 'hover:bg-gray-100 text-gray-700'
        }`}
        onClick={onSelect}
      >
        {editing ? (
          <input
            ref={inputRef}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={handleRename}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRename();
              if (e.key === 'Escape') {
                setTitle(session.title);
                setEditing(false);
              }
            }}
            className="flex-1 px-1 py-0.5 text-sm border border-blue-300 rounded outline-none focus:ring-1 focus:ring-blue-400"
            onClick={(e) => e.stopPropagation()}
            maxLength={50}
          />
        ) : (
          <span
            className="flex-1 truncate text-sm"
            onDoubleClick={() => setEditing(true)}
          >
            {session.title}
          </span>
        )}
        {/* Actions */}
        <div className="hidden group-hover:flex items-center gap-0.5 ml-1">
          <button
            className="p-0.5 text-gray-400 hover:text-gray-600 text-xs"
            title="重命名"
            onClick={(e) => { e.stopPropagation(); setEditing(true); }}
          >
            ✏️
          </button>
          <button
            className="p-0.5 text-xs text-gray-400 hover:text-red-500"
            title="删除"
            onClick={(e) => { e.stopPropagation(); setShowDeleteModal(true); }}
          >
            🗑️
          </button>
        </div>
      </div>

      {/* Delete confirmation modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setShowDeleteModal(false)}>
          <div className="bg-white rounded-lg shadow-xl p-5 mx-4 max-w-sm w-full" onClick={(e) => e.stopPropagation()}>
            <p className="text-sm text-gray-700 mb-4">确定要删除会话「{session.title}」吗？此操作不可撤销。</p>
            <div className="flex justify-end gap-2">
              <button
                className="px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-100 rounded transition-colors"
                onClick={() => setShowDeleteModal(false)}
              >
                取消
              </button>
              <button
                className="px-3 py-1.5 text-sm text-white bg-red-500 hover:bg-red-600 rounded transition-colors"
                onClick={handleDeleteConfirm}
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
