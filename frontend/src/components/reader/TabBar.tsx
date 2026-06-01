import type { DocumentTab } from '../../types';

interface TabBarProps {
  tabs: DocumentTab[];
  activeTabId: string | null;
  onSelect: (tabId: string) => void;
  onClose: (tabId: string) => void;
}

export default function TabBar({ tabs, activeTabId, onSelect, onClose }: TabBarProps) {
  if (tabs.length === 0) return null;

  return (
    <div className="flex items-center bg-white border-b border-gray-200 overflow-x-auto shrink-0">
      {tabs.map((tab) => {
        const isActive = tab.id === activeTabId;
        return (
          <div
            key={tab.id}
            className={`group flex items-center gap-1 px-3 py-1.5 text-xs cursor-pointer border-b-2 transition-colors shrink-0 max-w-[160px] ${
              isActive
                ? 'border-blue-500 text-blue-700 bg-blue-50'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
            }`}
            onClick={() => onSelect(tab.id)}
            title={tab.filename}
          >
            <span className="text-sm flex-shrink-0">
              {tab.isPdf ? '\u{1F4C4}' : '\u{1F4C3}'}
            </span>
            <span className="truncate">{tab.label}</span>
            <button
              className="flex-shrink-0 w-4 h-4 flex items-center justify-center rounded-full text-gray-400 hover:text-red-500 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-opacity"
              onClick={(e) => {
                e.stopPropagation();
                onClose(tab.id);
              }}
              title="关闭"
            >
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}
