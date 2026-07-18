import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { useNavigate } from 'react-router-dom';
import { LogOut, Shield, ShieldCheck, User as UserIcon, ChevronDown } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import type { Role } from '../api/types';

const ROLE_TONE: Record<Role, string> = {
  admin: 'bg-primary-50 text-primary-700',
  curator: 'bg-accent-100 text-accent-700',
};

export default function UserMenu() {
  const { user, logout, hasRole, requestAdmin } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  const handleLogout = async () => {
    await logout();
    toast.success('Signed out');
    navigate('/login');
  };

  const handleRequestAdmin = async () => {
    try {
      await requestAdmin();
      toast.success('Admin access requested — an admin will review it.');
    } catch {
      toast.error('Could not send the request. Please try again.');
    }
  };

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger aria-label="Account menu" className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white py-1.5 pl-1.5 pr-2.5 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 data-[state=open]:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800 dark:data-[state=open]:bg-slate-800">
        <span className="grid h-7 w-7 place-items-center rounded-lg bg-primary-600 text-white">
          <UserIcon className="h-4 w-4" />
        </span>
        <span className="hidden max-w-[10rem] truncate sm:block">{user.name || user.email}</span>
        <ChevronDown className="h-4 w-4 text-slate-400" />
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className="z-50 w-64 origin-top-right animate-fade-in rounded-2xl border border-slate-200 bg-white p-1.5 shadow-pop dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="flex items-center gap-3 px-3 py-2.5">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary-600 text-white">
              <UserIcon className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
                {user.name || 'Signed in'}
              </p>
              <p className="truncate text-xs text-slate-500 dark:text-slate-400">{user.email}</p>
              <span
                className={`mt-1.5 inline-block rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${ROLE_TONE[user.role]}`}
              >
                {user.role}
              </span>
            </div>
          </div>

          <DropdownMenu.Separator className="my-1 h-px bg-slate-100 dark:bg-slate-800" />

          <Item icon={<UserIcon className="h-4 w-4" />} onSelect={() => navigate('/profile')}>
            Profile &amp; sessions
          </Item>
          {user.role === 'curator' && (
            <Item
              icon={<ShieldCheck className="h-4 w-4" />}
              onSelect={user.admin_requested ? () => {} : handleRequestAdmin}
              className={user.admin_requested ? 'text-slate-400' : 'text-accent-700 focus:bg-accent-50'}
            >
              {user.admin_requested ? 'Admin access requested' : 'Request admin access'}
            </Item>
          )}
          {hasRole('admin') && (
            <Item icon={<Shield className="h-4 w-4" />} onSelect={() => navigate('/admin')}>
              Admin console
            </Item>
          )}

          <DropdownMenu.Separator className="my-1 h-px bg-slate-100 dark:bg-slate-800" />

          <Item
            icon={<LogOut className="h-4 w-4" />}
            onSelect={handleLogout}
            className="text-rose-600 focus:bg-rose-50"
          >
            Sign out
          </Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function Item({
  icon,
  children,
  onSelect,
  className = '',
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
  onSelect: () => void;
  className?: string;
}) {
  return (
    <DropdownMenu.Item
      onSelect={onSelect}
      className={`flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 outline-none transition focus:bg-slate-100 dark:text-slate-200 dark:focus:bg-slate-800 ${className}`}
    >
      {icon}
      {children}
    </DropdownMenu.Item>
  );
}
