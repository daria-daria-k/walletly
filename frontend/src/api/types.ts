export type Role = 'owner' | 'admin' | 'member';
export type TxType = 'income' | 'expense' | 'transfer';
export type Plan = 'free' | 'premium';

export interface User { id: number; email: string; name: string; role: 'user' | 'admin'; created_at: string }
export interface Ledger { id: number; name: string; type: 'personal' | 'shared'; owner_id: number; created_at: string; role: Role }
export interface Member { user_id: number; name: string; email: string; role: Role; joined_at: string }
export interface Account { id: number; name: string; currency: string; initial_balance: string; balance: string; is_active: boolean; sort_order: number }
export interface Category { id: number; category_group_id: number; name: string; is_active: boolean; sort_order: number }
export interface CategoryGroup { id: number; name: string; type: 'income' | 'expense'; sort_order: number; categories: Category[] }
export interface Transaction { id: number; ledger_id: number; user_id: number; author_name: string; type: TxType; amount: string; account_id: number; to_account_id: number | null; category_id: number | null; description: string | null; tx_date: string; created_at: string }
export interface TransactionPage { items: Transaction[]; total: number; limit: number; offset: number }
export interface Summary { income: string; expense: string; net: string }
export interface CategoryTotal { category_id: number; category_name: string; group_name: string; total: string }
export interface MonthTotal { month: string; income: string; expense: string }
export interface ImportResult { total_rows: number; created: number; skipped_duplicates: number; errors: { row: number; message: string }[]; dry_run: boolean }
export interface Invitation { id: number; email: string; token: string; status: 'pending' | 'accepted' | 'declined' | 'expired'; expires_at: string; created_at: string }
export interface InvitationPreview { ledger_name: string; invited_email: string; status: Invitation['status']; expires_at: string }
export interface AdminStats { users_total: number; users_active: number; users_premium: number; transactions_total: number }
export interface AdminUser { id: number; email: string; name: string; role: 'user' | 'admin'; is_active: boolean; plan: Plan; created_at: string }
