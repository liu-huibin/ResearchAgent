import { useState, useCallback, useRef } from 'react';

interface LayoutProps {
  sidebar: React.ReactNode;
  reader: React.ReactNode;
  chat: React.ReactNode;
}

export default function Layout({ sidebar, reader, chat }: LayoutProps) {
  const [leftWidth, setLeftWidth] = useState(15);
  const [rightWidth, setRightWidth] = useState(35);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef<'left' | 'right' | null>(null);

  const onMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      if (dragging.current === 'left') {
        setLeftWidth(Math.max(8, Math.min(25, pct)));
      } else {
        const leftPct = leftWidth;
        setRightWidth(100 - leftPct - Math.max(25, Math.min(50, pct)));
      }
    },
    [leftWidth]
  );

  const onMouseUp = useCallback(() => {
    dragging.current = null;
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, [onMouseMove]);

  const startDrag = (side: 'left' | 'right') => () => {
    dragging.current = side;
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const midWidth = 100 - leftWidth - rightWidth;

  return (
    <div ref={containerRef} className="flex h-full w-full bg-gray-50">
      {/* Left: Sidebar */}
      <div style={{ width: `${leftWidth}%` }} className="min-w-[180px] border-r border-gray-200 bg-white flex flex-col">
        {sidebar}
      </div>

      {/* Divider */}
      <div
        className="w-1 cursor-col-resize bg-gray-200 hover:bg-blue-400 transition-colors shrink-0"
        onMouseDown={startDrag('left')}
      />

      {/* Middle: Reader */}
      <div style={{ width: `${midWidth}%` }} className="flex flex-col bg-gray-100">
        {reader}
      </div>

      {/* Divider */}
      <div
        className="w-1 cursor-col-resize bg-gray-200 hover:bg-blue-400 transition-colors shrink-0"
        onMouseDown={startDrag('right')}
      />

      {/* Right: Chat */}
      <div style={{ width: `${rightWidth}%` }} className="min-w-[280px] bg-white flex flex-col">
        {chat}
      </div>
    </div>
  );
}
