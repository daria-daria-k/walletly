import { CreditCard, LayoutDashboard, LineChart, LogOut, Menu, Palette, Plus, ReceiptText, Settings, Shield, Upload, Users, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth';
import { initials } from '../lib/format';
import { useLedger } from '../ledger';
import { TransactionModal } from './TransactionModal';

const NAV = [
  { to: '/', label: 'Обзор', icon: LayoutDashboard },
  { to: '/transactions', label: 'Операции', icon: ReceiptText },
  { to: '/analytics', label: 'Аналитика', icon: LineChart },
  { to: '/accounts', label: 'Счета', icon: CreditCard },
  { to: '/categories', label: 'Категории', icon: Palette },
  { to: '/import', label: 'Импорт', icon: Upload },
  { to: '/family', label: 'Семья', icon: Users },
];

export const THEME_KEY = 'walletly-theme';

function storedTheme() {
  try {
    return localStorage.getItem(THEME_KEY) ?? 'violet';
  } catch {
    return 'violet';
  }
}

export function Layout() {
  const { user, logout } = useAuth();
  const { ledgers, ledger, select } = useLedger();
  const [menuOpen, setMenuOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [theme, setTheme] = useState(storedTheme);

  useEffect(() => {
    // Тему меняет страница настроек, а применяется она здесь, на корневом элементе
    const listener = (event: Event) => setTheme((event as CustomEvent<string>).detail);
    window.addEventListener(THEME_KEY, listener);
    return () => window.removeEventListener(THEME_KEY, listener);
  }, []);

  const closeMenu = () => setMenuOpen(false);
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? 'active' : '');

  return (
    <main className="app-shell" data-theme={theme}>
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <div className="brand"><span className="brand-mark">W</span><span>Walletly</span></div>
        <button className="mobile-close" onClick={closeMenu} aria-label="Закрыть меню"><X /></button>
        <nav className="nav-list" aria-label="Основная навигация">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} className={link} onClick={closeMenu}>
              <Icon size={19} /><span>{label}</span>
            </NavLink>
          ))}
          {user?.role === 'admin' && (
            <NavLink to="/admin" className={link} onClick={closeMenu}><Shield size={19} /><span>Админка</span></NavLink>
          )}
        </nav>
        <div className="nav-divider" />
        <p className="nav-caption">Пространство</p>
        <label className="family-chip">
          <Users size={19} />
          <select aria-label="Текущее пространство" value={ledger.id} onChange={(e) => select(Number(e.target.value))}>
            {ledgers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <div className="sidebar-bottom">
          <NavLink to="/settings" className={link} onClick={closeMenu}><Settings size={19} />Настройки</NavLink>
          <div className="profile-mini">
            <span>{initials(user?.name ?? '')}</span>
            <div><b>{user?.name}</b><small>{user?.email}</small></div>
          </div>
        </div>
      </aside>
      {menuOpen && <button className="overlay" aria-label="Закрыть меню" onClick={closeMenu} />}

      <section className="workspace">
        <header className="topbar">
          <button className="menu-button" onClick={() => setMenuOpen(true)} aria-label="Открыть меню"><Menu /></button>
          <div className="top-actions" style={{ marginLeft: 'auto' }}>
            <button className="primary-button" onClick={() => setAdding(true)}><Plus size={18} />Операция</button>
            <button className="icon-button" onClick={logout} aria-label="Выйти" title="Выйти"><LogOut size={20} /></button>
          </div>
        </header>
        <div className="content"><Outlet /></div>
      </section>
      {adding && <TransactionModal onClose={() => setAdding(false)} />}
    </main>
  );
}
