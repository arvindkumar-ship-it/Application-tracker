'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowUpRight, BriefcaseBusiness, ChevronRight, Database, FileInput, LayoutDashboard, List, Loader2, LogOut, Menu, Settings, ShieldCheck, X } from 'lucide-react';
import { api, ApiError } from '@/lib/api';
import type { Owner } from '@/lib/types';

export function Brand() { return <Link href="/" className="brand" aria-label="Job Portal home"><span className="brand-mark"><BriefcaseBusiness size={21} strokeWidth={1.8}/></span><span>Job Portal<span className="brand-small">ARVIND'S WORKSPACE</span></span></Link>; }
function Shell({children}: {children: React.ReactNode}) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [logoutError, setLogoutError] = useState('');
  const owner = useQuery({ queryKey: ['owner'], queryFn: () => api<Owner>('/auth/me'), enabled: pathname !== '/login', retry: false });
  useEffect(() => { if (owner.error instanceof ApiError && owner.error.status === 401 && pathname !== '/login') router.replace('/login'); }, [owner.error, pathname, router]);
  useEffect(() => { if (!mobileOpen) return; const previous = document.body.style.overflow; document.body.style.overflow = 'hidden'; const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setMobileOpen(false); }; document.addEventListener('keydown', close); return () => { document.body.style.overflow = previous; document.removeEventListener('keydown', close); }; }, [mobileOpen]);
  if (pathname === '/login') return <>{children}</>;
  if (owner.error instanceof ApiError && owner.error.status === 401) {
    return <main className="gate"><ShieldCheck size={30}/><h1>Your workspace is private.</h1><p>Sign in to access your job portal.</p><Link className="button primary" href="/login">Go to sign in <ChevronRight size={16}/></Link></main>;
  }
  if (owner.isLoading) return <main className="gate" role="status"><Loader2 className="spin"/><p>Opening your workspace…</p></main>;
  if (owner.error) return <main className="gate"><h1>Unable to open your workspace</h1><p>{owner.error.message}</p><button className="button primary" onClick={() => owner.refetch()}>Try again</button><Link href="/login">Back to sign in</Link></main>;
  const nav = [{label: 'Overview', Icon: LayoutDashboard, available: true}, {label: 'Job intake', Icon: FileInput}, {label: 'Master list', Icon: List}, {label: 'Your vault', Icon: Database}, {label: 'Settings', Icon: Settings}];
  return <div className="app-frame"><a className="skip-link" href="#main">Skip to content</a><aside id="workspace-navigation" className={`sidebar ${mobileOpen ? 'is-open' : ''}`}><div className="sidebar-head"><Brand/><button className="icon-button mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={20}/></button></div><div className="workspace-label">PERSONAL WORKSPACE</div><nav aria-label="Main navigation">{nav.map(({label, Icon, available}) => available ? <Link key={label} href="/" aria-current="page" className="nav-item active" onClick={() => setMobileOpen(false)}><Icon size={18}/>{label}</Link> : <div key={label} className="nav-item unavailable" aria-disabled="true" title="Available after the foundation phase passes"><Icon size={18}/>{label}<span className="soon">Later phase</span></div>)}</nav><div className="sidebar-bottom"><div className="trust-note"><ShieldCheck size={18}/><div><strong>Built on your facts</strong><p>Your experience. Your evidence.<br/>Always in your control.</p></div></div><div className="owner-row"><span className="avatar">A</span><div><strong>{owner.data?.full_name}</strong><span>Personal account</span></div><button className="icon-button" aria-label="Sign out" onClick={async () => { try { await api('/auth/logout', {method:'POST'}); queryClient.clear(); router.replace('/login'); } catch(e) { setLogoutError((e as Error).message); } }}><LogOut size={16}/></button></div>{logoutError && <p role="alert" className="error-text">{logoutError}</p>}</div></aside>{mobileOpen && <button className="mobile-overlay" aria-label="Dismiss navigation overlay" onClick={() => setMobileOpen(false)}/>}<div className="workspace"><header className="topbar"><div className="breadcrumb"><button className="icon-button menu-button" aria-label="Open navigation" aria-expanded={mobileOpen} aria-controls="workspace-navigation" onClick={() => setMobileOpen(true)}><Menu size={20}/></button><span>Workspace</span><ChevronRight size={14}/><strong>Overview</strong></div><span className="private-label"><ShieldCheck size={14}/> Private workspace</span></header><main id="main" className="page-content">{children}</main><footer className="app-footer"><span>Job Portal · Personal workspace</span><span>Display timezone · Asia/Kolkata <ArrowUpRight size={12}/></span></footer></div></div>;
}
export function AppShell({children}: {children: React.ReactNode}) {
  const [client] = useState(() => new QueryClient({defaultOptions:{queries:{staleTime:30_000,refetchOnWindowFocus:false}}}));
  return <QueryClientProvider client={client}><Shell>{children}</Shell></QueryClientProvider>;
}
