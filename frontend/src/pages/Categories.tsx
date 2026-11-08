import { Plus } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { api, errorText } from '../api/client';
import type { Category, CategoryGroup } from '../api/types';
import { ErrorNote, Modal, PageHeading, State } from '../components/ui';
import { useCategoryGroups, useRefreshLedgerData } from '../lib/data';
import { useLedger } from '../ledger';

function GroupModal({ onClose }: { onClose: () => void }) {
  const { base } = useLedger();
  const refresh = useRefreshLedgerData();
  const [name, setName] = useState('');
  const [type, setType] = useState('expense');
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await api(`${base}/category-groups`, { method: 'POST', body: { name, type, sort_order: 100 } });
      await refresh();
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <Modal eyebrow="Категории" title="Новая группа" onClose={onClose}>
      <form onSubmit={submit} style={{ marginTop: 16 }}>
        <label>Название<input value={name} onChange={(e) => setName(e.target.value)} maxLength={50} required autoFocus /></label>
        <label>Тип<select value={type} onChange={(e) => setType(e.target.value)}><option value="expense">Расходы</option><option value="income">Доходы</option></select></label>
        <ErrorNote text={error} />
        <button className="primary-button submit">Создать</button>
      </form>
    </Modal>
  );
}

function GroupCard({ group, canManage, run }: { group: CategoryGroup; canManage: boolean; run: (action: () => Promise<unknown>) => Promise<boolean> }) {
  const { base } = useLedger();
  const [newName, setNewName] = useState('');

  async function add(event: FormEvent) {
    event.preventDefault();
    const done = await run(() => api(`${base}/categories`, { method: 'POST', body: { category_group_id: group.id, name: newName, sort_order: group.categories.length } }));
    if (done) setNewName('');
  }

  function rename(category: Category) {
    const name = window.prompt('Новое название', category.name)?.trim();
    if (name && name !== category.name) run(() => api(`${base}/categories/${category.id}`, { method: 'PATCH', body: { name } }));
  }

  return (
    <section className="card category-group">
      <div className="group-head">
        <div><h3>{group.name}</h3><p>{group.type === 'income' ? 'Доходы' : 'Расходы'}</p></div>
        {canManage && group.categories.length === 0 && (
          <button className="small-button danger" onClick={() => run(() => api(`${base}/category-groups/${group.id}`, { method: 'DELETE' }))}>Удалить</button>
        )}
      </div>
      <div className="group-items">
        {group.categories.map((category) => (
          <div className={`category-line ${category.is_active ? '' : 'archived'}`} key={category.id}>
            <b>{category.name}</b>
            {canManage && (
              <div className="row-actions">
                <button className="small-button" onClick={() => rename(category)}>Имя</button>
                <button className="small-button" onClick={() => run(() => api(`${base}/categories/${category.id}`, { method: 'PATCH', body: { is_active: !category.is_active } }))}>{category.is_active ? 'Архив' : 'Вернуть'}</button>
                <button className="small-button danger" aria-label={`Удалить ${category.name}`} onClick={() => run(() => api(`${base}/categories/${category.id}`, { method: 'DELETE' }))}>×</button>
              </div>
            )}
          </div>
        ))}
        {canManage && (
          <form className="inline-form" onSubmit={add} style={{ marginTop: 10 }}>
            <input aria-label={`Новая категория в группе ${group.name}`} placeholder="Новая категория" value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={50} required />
            <button className="small-button">Добавить</button>
          </form>
        )}
      </div>
    </section>
  );
}

export function CategoriesPage() {
  const { canManage } = useLedger();
  const refresh = useRefreshLedgerData();
  const { data: groups, isLoading } = useCategoryGroups();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>): Promise<boolean> {
    setError(null);
    try {
      await action();
      await refresh();
      return true;
    } catch (err) {
      setError(errorText(err));
      return false;
    }
  }

  if (isLoading) return <State>Загрузка…</State>;

  return (
    <div className="prototype-page">
      <PageHeading eyebrow="Структура учёта" title="Категории" subtitle="Категории с операциями можно только архивировать." action={canManage ? <button className="primary-button" onClick={() => setCreating(true)}><Plus size={18} />Новая группа</button> : undefined} />
      <ErrorNote text={error} />
      <div className="category-groups wide">
        {groups?.map((group) => <GroupCard key={group.id} group={group} canManage={canManage} run={run} />)}
      </div>
      {creating && <GroupModal onClose={() => setCreating(false)} />}
    </div>
  );
}
