import { Link, Navigate, Outlet, Route, Routes, useLocation, useOutletContext } from 'react-router-dom';
import { useAuth } from './auth';
import { Layout } from './components/Layout';
import { StateCard, WalletlyPreloader } from './components/ui';
import { LedgerProvider } from './ledger';
import { AccountsPage } from './pages/Accounts';
import { AdminPage } from './pages/Admin';
import { AiPage } from './pages/Ai';
import { AnalyticsPage } from './pages/Analytics';
import { ForgotPasswordPage, LoginPage, RegisterPage, ResetPasswordPage, VerifyEmailPage } from './pages/Auth';
import { CategoriesPage } from './pages/Categories';
import { CategoryIconsPage } from './pages/CategoryIcons';
import { FamilyPage } from './pages/Family';
import { GoalsPage } from './pages/Goals';
import { ImportPage } from './pages/Import';
import { InvitePage } from './pages/Invite';
import { OnboardingPage } from './pages/Onboarding';
import { OverviewPage } from './pages/Overview';
import { SettingsPage } from './pages/Settings';
import { TransactionsPage } from './pages/Transactions';

function RequireAuth() {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  return <Outlet />;
}

function RequireOnboarding() {
  const { user } = useAuth();
  // Контекст Outlet не проходит сквозь вложенные маршруты сам: без этого страницы его не увидят
  const context = useOutletContext();
  return user?.onboarding_completed ? <Outlet context={context} /> : <Navigate to="/onboarding" replace />;
}

function NotFound() {
  return (
    <div className="state-page" data-theme="violet">
      <StateCard type="missing" title="Страница не найдена" text="Возможно, ссылка устарела или была удалена.">
        <Link className="secondary-button" to="/">На главную</Link>
      </StateCard>
    </div>
  );
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
  const location = useLocation();
  if (loading && location.pathname !== '/category-icons') return <WalletlyPreloader />;

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/category-icons" element={<CategoryIconsPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/invite/:token" element={<InvitePage />} />
        <Route element={<AppShell />}>
          <Route path="onboarding" element={<OnboardingPage />} />
          <Route element={<RequireOnboarding />}>
            <Route index element={<OverviewPage />} />
            <Route path="transactions" element={<TransactionsPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="accounts" element={<AccountsPage />} />
            <Route path="categories" element={<CategoriesPage />} />
            <Route path="goals" element={<GoalsPage />} />
            <Route path="import" element={<ImportPage />} />
            <Route path="family" element={<FamilyPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="admin" element={<AdminPage />} />
            <Route path="ai" element={<AiPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
