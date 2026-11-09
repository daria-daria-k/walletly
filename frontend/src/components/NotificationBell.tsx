import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { NotificationItem, NotificationList } from '../api/types';
import { dateTime } from '../lib/format';

const KEY = ['notifications'];

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // Раз в минуту: новые уведомления появляются по расписанию, push здесь не нужен
  const { data } = useQuery({ queryKey: KEY, queryFn: () => api<NotificationList>('/notifications'), refetchInterval: 60_000 });
  const unread = data?.unread ?? 0;

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  async function pick(item: NotificationItem) {
    setOpen(false);
    if (!item.read_at) {
      await api(`/notifications/${item.id}/read`, { method: 'POST' });
      await queryClient.invalidateQueries({ queryKey: KEY });
    }
    navigate(item.link);
  }

  async function readAll() {
    await api('/notifications/read-all', { method: 'POST' });
    await queryClient.invalidateQueries({ queryKey: KEY });
  }

  return (
    <div className="notif" ref={root}>
      <button className="icon-button notif-button" aria-label={unread ? `Уведомления: ${unread} новых` : 'Уведомления'} aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <Bell size={20} />
        {unread > 0 && <i>{unread > 9 ? '9+' : unread}</i>}
      </button>
      {open && (
        <div className="notif-panel card">
          <header><b>Уведомления</b>{unread > 0 && <button onClick={readAll}>Прочитать все</button>}</header>
          {data?.items.length ? data.items.map((item) => (
            <button key={item.id} className={item.read_at ? 'notif-item' : 'notif-item unread'} onClick={() => pick(item)}>
              <b>{item.title}</b><span>{item.body}</span><small>{dateTime(item.created_at)}</small>
            </button>
          )) : <p>Пока ничего нового</p>}
        </div>
      )}
    </div>
  );
}
