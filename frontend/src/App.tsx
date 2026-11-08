import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from './auth';
import { Layout } from './components/Layout';
import { State } from './components/ui';
import { LedgerProvider } from './ledger';
import { AccountsPage } from './pages/Accounts';
import { AdminPage } from './pages/Admin';
import { AnalyticsPage } from './pages/Analytics';
import { LoginPage, RegisterPage } from './pages/Auth';
import { CategoriesPage } from './pages/Categories';
import { FamilyPage } from './pages/Family';
import { ImportPage } from './pages/Import';
import { InvitePage } from './pages/Invite';
import { OverviewPage } from './pages/Overview';
import { SettingsPage } from './pages/Settings';
import { TransactionsPage } from './pages/Transactions';

function RequireAuth() {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  return <Outlet />;
}

function AppShell() {
  return (
    <LedgerProvider>
      <Layout />
    </LedgerProvider>
  );
}

export function App() {
  const { loading } = useAuth();
  if (loading) return <State>Загрузка…</State>;

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/invite/:token" element={<InvitePage />} />
        <Route element={<AppShell />}>
          <Route index element={<OverviewPage />} />
          <Route path="transactions" element={<TransactionsPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="accounts" element={<AccountsPage />} />
          <Route path="categories" element={<CategoriesPage />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="family" element={<FamilyPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="admin" element={<AdminPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
