export type Role = 'owner' | 'admin' | 'member';
export type TxType = 'income' | 'expense' | 'transfer';
export type Plan = 'free' | 'premium';

export type AccountKind = 'card' | 'savings' | 'deposit' | 'cash';
export interface NotificationSettings { budget: boolean; unusual: boolean; weekly: boolean; family: boolean }
export interface User { id: number; email: string; name: string; role: 'user' | 'admin'; created_at: string; onboarding_completed: boolean; notifications: NotificationSettings; email_verified_at: string | null; plan?: Plan; plan_expires_at?: string | null }
export interface Ledger { id: number; name: string; type: 'personal' | 'shared'; owner_id: number; created_at: string; role: Role }
export interface Member { user_id: number; name: string; email: string; role: Role; joined_at: string }
export interface Account { id: number; name: string; currency: string; kind: AccountKind; initial_balance: string; balance: string; month_change: string; is_active: boolean; sort_order: number }
export interface Category { id: number; category_group_id: number; name: string; monthly_limit: string | null; is_active: boolean; sort_order: number }
export interface CategoryGroup { id: number; name: string; type: 'income' | 'expense'; sort_order: number; categories: Category[] }
export interface Transaction { id: number; ledger_id: number; user_id: number; author_name: string; type: TxType; amount: string; account_id: number; to_account_id: number | null; category_id: number | null; description: string | null; tx_date: string; created_at: string }
export interface TransactionPage { items: Transaction[]; total: number; limit: number; offset: number }
export interface Summary { income: string; expense: string; net: string }
export interface CategoryTotal { category_id: number; category_name: string; group_name: string; total: string }
export interface AuthorTotal { user_id: number; name: string; total: string }
export interface MonthTotal { month: string; income: string; expense: string }
export interface ImportResult { total_rows: number; created: number; skipped_duplicates: number; errors: { row: number; message: string }[]; dry_run: boolean }
export interface Invitation { id: number; email: string; token: string; status: 'pending' | 'accepted' | 'declined' | 'expired'; expires_at: string; created_at: string }
export interface InvitationPreview { ledger_name: string; invited_email: string; status: Invitation['status']; expires_at: string }
export interface AdminStats { users_total: number; users_active: number; users_premium: number; users_new_30d: number; transactions_total: number; registrations: { week_start: string; count: number }[] }
export interface AdminUser { id: number; email: string; name: string; role: 'user' | 'admin'; is_active: boolean; plan: Plan; created_at: string }

export interface Goal { id: number; ledger_id: number; name: string; target_amount: string; monthly_contribution: string; account_id: number; account_name: string; currency: string; reminder_day: number; saved: string; remaining: string; progress_percent: number; months_left: number; forecast_month: string | null; contributed_this_month: boolean; missed_last_month: boolean; reminder_due: boolean }
export interface ContributionItem { id: number; user_name: string; amount: string; contributed_on: string; from_transfer: boolean; created_at: string }
export interface ImportBatch { id: number; filename: string; total_rows: number; created: number; skipped_duplicates: number; errors: number; created_at: string }
export interface AuditEntry { id: number; actor_email: string; target_email: string; action: string; detail: string; created_at: string }
export interface Insights {
  forecast: { spent: string; projected: string; baseline: string | null; change_percent: number | null; month_progress: number };
  anomaly: { transaction_id: number; title: string; category_name: string; amount: string; ratio: string; tx_date: string } | null;
  overspend: { category_id: number; category_name: string; amount: string } | null;
  limits: { total: number; near: number; over: number };
  plan: { category_id: number; category_name: string; average: string; has_limit: boolean }[];
  potential: string;
}
