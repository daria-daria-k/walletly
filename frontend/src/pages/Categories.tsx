import { useQuery } from '@tanstack/react-query';
import { MoreHorizontal, Plus } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { api, errorText } from '../api/client';
import type { Category, CategoryGroup, CategoryTotal } from '../api/types';
import { StyledSelect } from '../components/StyledSelect';
import { ErrorNote, ErrorState, LoadingState, Modal, PageHeading } from '../components/ui';
import { useCategoryGroups, useRefreshLedgerData } from '../lib/data';
import { money, monthRange } from '../lib/format';
import { useLedger } from '../ledger';

const GROUP_HINT: Record<string, string> = {
  Базовые: 'Обязательные регулярные расходы',
  Текущие: 'Повседневные переменные траты',
  Крупные: 'Планируемые покупки и цели',
  Доходы: 'Источники поступлений',
};

function useAct(onDone: () => void) {
  const refresh = useRefreshLedgerData();
  const [error, setError] = useState<string | null>(null);
  async function act(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      await refresh();
      onDone();
    } catch (err) {
      setError(errorText(err));
    }
  }
  return { error, act };
}

function GroupModal({ group, onClose }: { group?: CategoryGroup; onClose: () => void }) {
  const { base } = useLedger();
  const { error, act } = useAct(onClose);
  const [name, setName] = useState(group?.name ?? '');
  const [type, setType] = useState('expense');

  function submit(event: FormEvent) {
    event.preventDefault();
    act(() => (group ? api(`${base}/category-groups/${group.id}`, { method: 'PATCH', body: { name } }) : api(`${base}/category-groups`, { method: 'POST', body: { name, type, sort_order: 100 } })));
  }

  return (
    <Modal eyebrow="Категории" title={group ? 'Изменить группу' : 'Новая группа'} onClose={onClose}>
      <form onSubmit={submit} style={{ marginTop: 16 }}>
        <label>Название<input value={name} onChange={(e) => setName(e.target.value)} maxLength={50} required autoFocus /></label>
        {!group && <label>Тип<StyledSelect ariaLabel="Тип группы" value={type} onChange={setType} options={[{ value: 'expense', label: 'Расходы' }, { value: 'income', label: 'Доходы' }]} /></label>}
        <ErrorNote text={error} />
        <button className="primary-button submit">Сохранить</button>
        {group && <button type="button" className="danger-button" onClick={() => act(() => api(`${base}/category-groups/${group.id}`, { method: 'DELETE' }))}>Удалить группу</button>}
      </form>
    </Modal>
  );
}

function CategoryModal({ groups, category, groupId, onClose }: { groups: CategoryGroup[]; category?: Category; groupId?: number; onClose: () => void }) {
  const { base } = useLedger();
  const { error, act } = useAct(onClose);
  const [name, setName] = useState(category?.name ?? '');
  const [group, setGroup] = useState(String(category?.category_group_id ?? groupId ?? groups.find((g) => g.type === 'expense')?.id ?? ''));
  const [limit, setLimit] = useState(category?.monthly_limit ?? '');
  const selected = groups.find((g) => String(g.id) === group);

  function submit(event: FormEvent) {
    event.preventDefault();
    const monthly_limit = selected?.type === 'expense' && String(limit).trim() ? String(limit).replace(/\s/g, '').replace(',', '.') : null;
    const body = { name, category_group_id: Number(group), monthly_limit };
    act(() => (category ? api(`${base}/categories/${category.id}`, { method: 'PATCH', body }) : api(`${base}/categories`, { method: 'POST', body })));
  }

  return (
    <Modal eyebrow="Категории" title={category ? 'Изменить категорию' : 'Новая категория'} onClose={onClose}>
      <form onSubmit={submit} style={{ marginTop: 16 }}>
        <label>Название<input value={name} onChange={(e) => setName(e.target.value)} maxLength={50} required autoFocus /></label>
        <label>Группа<StyledSelect ariaLabel="Группа" value={group} onChange={setGroup} options={groups.filter((g) => !category || g.type === groups.find((x) => x.id === category.category_group_id)?.type).map((g) => ({ value: String(g.id), label: g.name }))} /></label>
        {selected?.type === 'expense' && <label>Лимит в месяц, необязательно<input inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)} placeholder="Без лимита" /></label>}
        <ErrorNote text={error} />
        <button className="primary-button submit">Сохранить</button>
        {category && (
          <>
            <button type="button" className="secondary-button" onClick={() => act(() => api(`${base}/categories/${category.id}`, { method: 'PATCH', body: { is_active: !category.is_active } }))}>{category.is_active ? 'Отправить в архив' : 'Вернуть из архива'}</button>
            <button type="button" className="danger-button" onClick={() => act(() => api(`${base}/categories/${category.id}`, { method: 'DELETE' }))}>Удалить категорию</button>
          </>
        )}
      </form>
    </Modal>
  );
}

type Dialog = { kind: 'group'; group?: CategoryGroup } | { kind: 'category'; category?: Category; groupId?: number };

export function CategoriesPage() {
  const { base, canManage } = useLedger();
  const { data: groups, isLoading, isError, refetch } = useCategoryGroups();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const range = monthRange();
  const { data: spent = [] } = useQuery({ queryKey: [base, 'by-category', range], queryFn: () => api<CategoryTotal[]>(`${base}/analytics/by-category`, { query: range }) });
  const { data: earned = [] } = useQuery({ queryKey: [base, 'by-category', 'income', range], queryFn: () => api<CategoryTotal[]>(`${base}/analytics/by-category`, { query: { ...range, type: 'income' } }) });

  if (isLoading) return <LoadingState />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;

  const totals = new Map([...spent, ...earned].map((row) => [row.category_id, Number(row.total)]));
  const close = () => setDialog(null);
  // Как в дизайне: сначала группы расходов, доходы в конце
  const ordered = [...(groups ?? [])].sort((a, b) => Number(a.type === 'income') - Number(b.type === 'income'));

  return (
    <div className="prototype-page">
      <PageHeading eyebrow="Структура бюджета" title="Категории и лимиты" subtitle="Распределяйте расходы по понятным группам." action={canManage ? <button className="primary-button" onClick={() => setDialog({ kind: 'category' })}><Plus size={18} />Новая категория</button> : undefined} />
      <div className="category-groups wide">
        {ordered.map((group, index) => (
          <section className="card category-group" key={group.id}>
            <div className="group-head">
              <span className={`group-number g${(index % 3) + 1}`}>{index + 1}</span>
              <div><h3>{group.name}</h3><p>{GROUP_HINT[group.name] ?? (group.type === 'income' ? 'Доходы' : 'Расходы')}</p></div>
              {canManage && <button aria-label={`Настроить группу ${group.name}`} onClick={() => setDialog({ kind: 'group', group })}><MoreHorizontal /></button>}
            </div>
            <div className="group-items">
              {group.categories.map((category) => {
                const total = totals.get(category.id) ?? 0;
                const limit = Number(category.monthly_limit ?? 0);
                const percent = limit ? Math.round((total / limit) * 100) : null;
                const body = (
                  <>
                    <div><b>{category.name}</b><span>{money(total)}</span></div>
                    {percent !== null && <div className="progress"><span style={{ width: `${Math.min(100, percent)}%`, background: percent > 100 ? 'var(--coral)' : undefined }} /></div>}
                    <small>{!category.is_active ? 'В архиве' : percent !== null ? `${percent}% лимита · ${money(limit)}` : group.type === 'expense' ? 'Без лимита' : 'В этом месяце'}</small>
                  </>
                );
                return canManage
                  ? <button key={category.id} className={`budget-item editable ${category.is_active ? '' : 'archived'}`} onClick={() => setDialog({ kind: 'category', category })}>{body}</button>
                  : <div key={category.id} className={`budget-item ${category.is_active ? '' : 'archived'}`}>{body}</div>;
              })}
              {canManage && <button className="add-row" onClick={() => setDialog({ kind: 'category', groupId: group.id })}><Plus size={15} />Добавить категорию</button>}
            </div>
          </section>
        ))}
        {canManage && (
          <section className="card category-group" style={{ alignSelf: 'start' }}>
            <div className="group-items"><button className="add-row" onClick={() => setDialog({ kind: 'group' })}><Plus size={15} />Новая группа</button></div>
          </section>
        )}
      </div>
      {dialog?.kind === 'group' && <GroupModal group={dialog.group} onClose={close} />}
      {dialog?.kind === 'category' && groups && <CategoryModal groups={groups} category={dialog.category} groupId={dialog.groupId} onClose={close} />}
    </div>
  );
}
