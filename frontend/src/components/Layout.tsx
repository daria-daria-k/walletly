import { Bell, BrainCircuit, CreditCard, FileUp, LayoutDashboard, LineChart, LogOut, Menu, Palette, PiggyBank, Plus, ReceiptText, Search, Settings, ShieldCheck, Users, X } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate, useOutletContext } from 'react-router-dom';
import type { TxType } from '../api/types';
import { useAuth } from '../auth';
import { initials } from '../lib/format';
import { useLedger } from '../ledger';
import { StyledSelect } from './StyledSelect';
import { TransactionModal } from './TransactionModal';

const NAV = [
  { to: '/', label: 'Обзор', icon: LayoutDashboard },
  { to: '/transactions', label: 'Транзакции', icon: ReceiptText },
  { to: '/analytics', label: 'Аналитика', icon: LineChart },
  { to: '/accounts', label: 'Счета', icon: CreditCard },
  { to: '/categories', label: 'Категории', icon: Palette },
  { to: '/goals', label: 'Копилка', icon: PiggyBank },
  { to: '/family', label: 'Семья', icon: Users },
];

const SERVICE_NAV = [
  { to: '/import', label: 'Импорт и экспорт', icon: FileUp },
  { to: '/ai', label: 'Walletly AI', icon: BrainCircuit },
];

export const THEME_KEY = 'walletly-theme';

function storedTheme() {
  try {
    return localStorage.getItem(THEME_KEY) ?? 'violet';
  } catch {
    return 'violet';
  }
}

export interface AddPreset {
  type?: TxType;
  account_id?: number;
}

export function useAddOperation() {
  return useOutletContext<{ openAdd: (preset?: AddPreset) => void }>().openAdd;
}

export function Layout() {
  const { user, logout } = useAuth();
  const { ledgers, ledger, select } = useLedger();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [adding, setAdding] = useState<AddPreset | null>(null);
  const [theme, setTheme] = useState(storedTheme);
  const [search, setSearch] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Тему меняет страница настроек, а применяется она здесь, на корневом элементе
    const listener = (event: Event) => setTheme((event as CustomEvent<string>).detail);
    window.addEventListener(THEME_KEY, listener);
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener(THEME_KEY, listener);
      window.removeEventListener('keydown', onKey);
    };
  }, []);

  useEffect(() => {
    // Выпадающие списки рисуются в body, вне .app-shell, и должны видеть те же цвета темы
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const closeMenu = () => setMenuOpen(false);
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? 'active' : '');

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    navigate(`/transactions?search=${encodeURIComponent(search.trim())}`);
    setSearch('');
  }

  return (
    <main className="app-shell" data-theme={theme}>
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <div className="brand"><img className="brand-mark" src="/brand/walletly-mark.svg" alt="" /><span>Walletly</span></div>
        <button className="mobile-close" onClick={closeMenu} aria-label="Закрыть меню"><X /></button>
        <nav className="nav-list" aria-label="Основная навигация">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} className={link} onClick={closeMenu}>
              <Icon size={19} /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="nav-divider" />
        <p className="nav-caption">Пространство</p>
        <div className="family-chip">
          <Users size={19} />
          <StyledSelect ariaLabel="Текущее пространство" value={String(ledger.id)} onChange={(value) => select(Number(value))} options={ledgers.map((item) => ({ value: String(item.id), label: item.name }))} />
        </div>
        <div className="nav-divider" />
        <p className="nav-caption">Дополнительно</p>
        <nav className="nav-list service-nav" aria-label="Дополнительные разделы">
          {SERVICE_NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={link} onClick={closeMenu}><Icon size={18} /><span>{label}</span></NavLink>
          ))}
          {user?.role === 'admin' && (
            <NavLink to="/admin" className={link} onClick={closeMenu}><ShieldCheck size={18} /><span>Администратор</span></NavLink>
          )}
        </nav>
        <div className="sidebar-bottom">
          <NavLink to="/settings" className={link} onClick={closeMenu}><Settings size={19} />Настройки</NavLink>
          <div className="profile-mini">
            <span>{initials(user?.name ?? '')}</span>
            <div><b>{user?.name}</b><small>{user?.plan === 'premium' ? 'Premium' : 'Free'}</small></div>
            <button onClick={logout} aria-label="Выйти" title="Выйти"><LogOut size={16} /></button>
          </div>
        </div>
      </aside>
      {menuOpen && <button className="overlay" aria-label="Закрыть меню" onClick={closeMenu} />}

      <section className="workspace">
        <header className="topbar">
          <button className="menu-button" onClick={() => setMenuOpen(true)} aria-label="Открыть меню"><Menu /></button>
          <form className="search" onSubmit={submitSearch} role="search">
            <Search size={18} />
            <input ref={searchRef} aria-label="Поиск" placeholder="Найти транзакцию" value={search} onChange={(e) => setSearch(e.target.value)} />
            <kbd>⌘ K</kbd>
          </form>
          <div className="top-actions">
            <button className="icon-button" aria-label="Уведомления" title="Уведомлений нет"><Bell size={20} /></button>
            <Link className="avatar" to="/settings" aria-label="Профиль">{initials(user?.name ?? '')}</Link>
          </div>
        </header>
        <div className="content"><Outlet context={{ openAdd: (preset: AddPreset = {}) => setAdding(preset) }} /></div>
        {/* На онбординге счетов ещё нет: «+» открыл бы пустую форму, а разделы всё равно вернут на настройку */}
        {pathname !== '/onboarding' && (
          <nav className="mobile-nav" aria-label="Мобильная навигация">
            {NAV.slice(0, 4).map(({ to, label, icon: Icon }) => (
              <button key={to} className={pathname === to ? 'active' : ''} onClick={() => navigate(to)}><Icon size={20} /><span>{label}</span></button>
            ))}
            <button onClick={() => setAdding({})}><span className="mobile-add"><Plus /></span><span>Добавить</span></button>
          </nav>
        )}
      </section>
      {adding && <TransactionModal preset={adding} onClose={() => setAdding(null)} />}
    </main>
  );
}
