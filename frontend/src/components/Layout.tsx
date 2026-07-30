import { useEffect, useRef, useState } from 'react';

interface LayoutProps {
  sidebar: React.ReactNode;
  reader: React.ReactNode;
  chat: React.ReactNode;
}

export default function Layout({ sidebar, reader, chat }: LayoutProps) {
  const [leftWidth, setLeftWidth] = useState(15);
  const [rightWidth, setRightWidth] = useState(35);
  const [dragging, setDragging] = useState<'left' | 'right' | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!dragging) return;

    const onMouseMove = (event: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pointerPct = ((event.clientX - rect.left) / rect.width) * 100;

      if (dragging === 'left') {
        setLeftWidth(Math.max(8, Math.min(25, pointerPct)));
      } else {
        setRightWidth(Math.max(25, Math.min(50, 100 - pointerPct)));
      }
    };
    const onMouseUp = () => setDragging(null);

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    return () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [dragging]);

  const midWidth = 100 - leftWidth - rightWidth;

  return (
    <div ref={containerRef} className="flex h-full w-full bg-gray-50">
      <div style={{ width: `${leftWidth}%` }} className="min-w-[180px] border-r border-gray-200 bg-white flex flex-col">
        {sidebar}
      </div>

      <div
        className="w-1 cursor-col-resize bg-gray-200 hover:bg-blue-400 transition-colors shrink-0"
        onMouseDown={() => setDragging('left')}
      />

      <div style={{ width: `${midWidth}%` }} className="flex flex-col bg-gray-100">
        {reader}
      </div>

      <div
        className="w-1 cursor-col-resize bg-gray-200 hover:bg-blue-400 transition-colors shrink-0"
        onMouseDown={() => setDragging('right')}
      />

      <div style={{ width: `${rightWidth}%` }} className="min-w-[280px] bg-white flex flex-col">
        {chat}
      </div>
    </div>
  );
}
