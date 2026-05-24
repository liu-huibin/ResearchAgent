import SessionItem from './SessionItem';
import type { Session } from '../../types';

interface SessionListProps {
  sessions: Session[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
  onRename: (id: number, title: string) => void;
}

export default function SessionList({
  sessions, activeId, onSelect, onDelete, onRename,
}: SessionListProps) {
  return (
    <div className="py-1">
      {sessions.map((s) => (
        <SessionItem
          key={s.id}
          session={s}
          isActive={s.id === activeId}
          onSelect={() => onSelect(s.id)}
          onDelete={() => onDelete(s.id)}
          onRename={(title) => onRename(s.id, title)}
        />
      ))}
    </div>
  );
}
