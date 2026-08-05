import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, Image, LifeBuoy, MessageSquare, Paperclip, Send } from 'lucide-react';
import { toast } from 'sonner';
import PageHeader from '../components/ui/PageHeader';
import { Card, CardBody } from '../components/ui/Card';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';
import { EmptyState, LoadingBlock } from '../components/ui/Feedback';
import { useAuth } from '../context/AuthContext';
import {
  createSupportTicket,
  downloadSupportScreenshot,
  listSupportTickets,
  replySupportTicket,
  updateSupportStatus,
  type SupportCategory,
  type SupportStatus,
  type SupportTicket,
} from '../api/support';

const CATEGORY_LABEL: Record<SupportCategory, string> = {
  question: 'Question',
  bug: 'Problem / bug',
  data: 'Data or mapping issue',
  feature: 'Feature request',
  other: 'Other',
};

const STATUS_TONE: Record<SupportStatus, 'amber' | 'primary' | 'green'> = {
  open: 'amber',
  in_progress: 'primary',
  resolved: 'green',
};

export default function SupportPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const tickets = useQuery({ queryKey: ['support'], queryFn: listSupportTickets });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [category, setCategory] = useState<SupportCategory>('question');
  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const [reply, setReply] = useState('');

  useEffect(() => {
    if (selectedId == null && tickets.data?.length) setSelectedId(tickets.data[0].id);
  }, [selectedId, tickets.data]);

  const refresh = () => qc.invalidateQueries({ queryKey: ['support'] });
  const createM = useMutation({
    mutationFn: createSupportTicket,
    onSuccess: (ticket) => {
      refresh();
      setSelectedId(ticket.id);
      setSubject('');
      setDescription('');
      setScreenshot(null);
      toast.success(`Support request #${ticket.id} sent`);
    },
    onError: (error: any) => toast.error(error?.message ?? 'Could not send support request'),
  });
  const replyM = useMutation({
    mutationFn: ({ id, body }: { id: number; body: string }) => replySupportTicket(id, body),
    onSuccess: () => {
      refresh();
      setReply('');
      toast.success('Reply sent');
    },
    onError: (error: any) => toast.error(error?.message ?? 'Could not send reply'),
  });
  const statusM = useMutation({
    mutationFn: ({ id, status }: { id: number; status: SupportStatus }) => updateSupportStatus(id, status),
    onSuccess: refresh,
    onError: (error: any) => toast.error(error?.message ?? 'Could not update status'),
  });

  const selected = tickets.data?.find((ticket) => ticket.id === selectedId) ?? null;
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (screenshot && screenshot.size > 5 * 1024 * 1024) {
      toast.error('Screenshot must be 5 MB or smaller');
      return;
    }
    createM.mutate({ category, subject: subject.trim(), description: description.trim(), screenshot });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Support"
        description={user?.role === 'admin' ? 'Ask for help or manage team support requests.' : 'Ask the MetaHarmonizer team a question or report an issue.'}
        icon={<LifeBuoy className="h-6 w-6" />}
      />

      <Card>
        <CardBody>
          <form onSubmit={submit} className="grid gap-4 lg:grid-cols-[180px_1fr_1fr_auto] lg:items-end">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
              Category
              <select className="field mt-1.5" value={category} onChange={(event) => setCategory(event.target.value as SupportCategory)}>
                {Object.entries(CATEGORY_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
              Subject
              <input className="field mt-1.5" required minLength={3} maxLength={200} value={subject} onChange={(event) => setSubject(event.target.value)} />
            </label>
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
              Screenshot (optional)
              <span className="field mt-1.5 flex items-center gap-2 overflow-hidden">
                <Paperclip className="h-4 w-4 shrink-0 text-slate-400" />
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  className="min-w-0 text-xs"
                  onChange={(event) => setScreenshot(event.target.files?.[0] ?? null)}
                />
              </span>
            </label>
            <Button type="submit" loading={createM.isPending} icon={<Send className="h-4 w-4" />}>Send</Button>
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300 lg:col-span-4">
              Details
              <textarea
                className="field mt-1.5 min-h-28 resize-y"
                required
                minLength={10}
                maxLength={10000}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
          </form>
        </CardBody>
      </Card>

      {tickets.isLoading ? <LoadingBlock /> : !tickets.data?.length ? (
        <Card><EmptyState icon={<MessageSquare className="h-6 w-6" />} title="No support requests yet" /></Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
          <div className="space-y-2">
            {tickets.data.map((ticket) => (
              <button
                key={ticket.id}
                type="button"
                onClick={() => setSelectedId(ticket.id)}
                className={`w-full rounded-lg border p-3 text-left transition ${selectedId === ticket.id ? 'border-primary-400 bg-primary-50 dark:border-primary-500 dark:bg-primary-500/10' : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-700 dark:bg-slate-900'}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-slate-400">#{ticket.id} · {CATEGORY_LABEL[ticket.category]}</span>
                  <Badge tone={STATUS_TONE[ticket.status]}>{ticket.status.replace('_', ' ')}</Badge>
                </div>
                <p className="mt-1 truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{ticket.subject}</p>
                {user?.role === 'admin' && <p className="mt-0.5 truncate text-xs text-slate-500">{ticket.creator_email}</p>}
              </button>
            ))}
          </div>
          {selected && (
            <TicketDetail
              ticket={selected}
              isAdmin={user?.role === 'admin'}
              reply={reply}
              setReply={setReply}
              replying={replyM.isPending}
              onReply={() => replyM.mutate({ id: selected.id, body: reply.trim() })}
              onStatus={(status) => statusM.mutate({ id: selected.id, status })}
            />
          )}
        </div>
      )}
    </div>
  );
}

function TicketDetail({
  ticket, isAdmin, reply, setReply, replying, onReply, onStatus,
}: {
  ticket: SupportTicket;
  isAdmin: boolean;
  reply: string;
  setReply: (value: string) => void;
  replying: boolean;
  onReply: () => void;
  onStatus: (status: SupportStatus) => void;
}) {
  return (
    <Card>
      <CardBody className="space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-slate-400">Request #{ticket.id}</p>
            <h2 className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-100">{ticket.subject}</h2>
            <p className="mt-1 text-xs text-slate-500">{ticket.creator_name || ticket.creator_email} · {new Date(ticket.created_at).toLocaleString()}</p>
          </div>
          {isAdmin ? (
            <select className="field !w-auto !py-1.5 text-xs" value={ticket.status} onChange={(event) => onStatus(event.target.value as SupportStatus)}>
              <option value="open">Open</option><option value="in_progress">In progress</option><option value="resolved">Resolved</option>
            </select>
          ) : <Badge tone={STATUS_TONE[ticket.status]}>{ticket.status.replace('_', ' ')}</Badge>}
        </div>
        <p className="whitespace-pre-wrap text-sm leading-6 text-slate-700 dark:text-slate-300">{ticket.description}</p>
        {ticket.has_screenshot && (
          <Button
            size="sm"
            variant="secondary"
            icon={<Image className="h-4 w-4" />}
            onClick={() => void downloadSupportScreenshot(ticket).catch(() => toast.error('Could not download screenshot'))}
          >
            {ticket.screenshot_name || 'Download screenshot'} <Download className="h-3.5 w-3.5" />
          </Button>
        )}
        {ticket.replies.length > 0 && (
          <div className="space-y-3 border-t border-slate-100 pt-4 dark:border-slate-800">
            {ticket.replies.map((item) => (
              <div key={item.id} className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
                <div className="flex justify-between gap-3 text-xs text-slate-500">
                  <span className="font-semibold">{item.author_name || item.author_email} · {item.author_role}</span>
                  <span>{new Date(item.created_at).toLocaleString()}</span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">{item.body}</p>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-2 border-t border-slate-100 pt-4 dark:border-slate-800">
          <textarea className="field min-h-20 flex-1 resize-y" maxLength={5000} value={reply} onChange={(event) => setReply(event.target.value)} />
          <Button disabled={!reply.trim()} loading={replying} onClick={onReply} icon={<Send className="h-4 w-4" />}>Reply</Button>
        </div>
      </CardBody>
    </Card>
  );
}
