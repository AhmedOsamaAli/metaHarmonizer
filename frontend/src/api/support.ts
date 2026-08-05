import { apiFetch, BASE, getAccessToken } from './http';

export type SupportCategory = 'question' | 'bug' | 'data' | 'feature' | 'other';
export type SupportStatus = 'open' | 'in_progress' | 'resolved';

export interface SupportReply {
    id: number;
    author_id: number;
    author_name: string | null;
    author_email: string;
    author_role: string;
    body: string;
    created_at: string;
}

export interface SupportTicket {
    id: number;
    created_by: number;
    creator_name: string | null;
    creator_email: string;
    creator_role: string;
    category: SupportCategory;
    subject: string;
    description: string;
    status: SupportStatus;
    screenshot_name: string | null;
    has_screenshot: boolean;
    created_at: string;
    updated_at: string;
    replies: SupportReply[];
}

export async function listSupportTickets(): Promise<SupportTicket[]> {
    return apiFetch<SupportTicket[]>('/support');
}

export async function createSupportTicket(input: {
    category: SupportCategory;
    subject: string;
    description: string;
    screenshot?: File | null;
}): Promise<SupportTicket> {
    const form = new FormData();
    form.set('category', input.category);
    form.set('subject', input.subject);
    form.set('description', input.description);
    if (input.screenshot) form.set('screenshot', input.screenshot);
    return apiFetch<SupportTicket>('/support', { method: 'POST', body: form });
}

export async function replySupportTicket(id: number, body: string): Promise<SupportTicket> {
    return apiFetch<SupportTicket>(`/support/${id}/replies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body }),
    });
}

export async function updateSupportStatus(
    id: number,
    status: SupportStatus,
): Promise<SupportTicket> {
    return apiFetch<SupportTicket>(`/support/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
    });
}

export async function downloadSupportScreenshot(ticket: SupportTicket): Promise<void> {
    const headers = new Headers();
    const token = getAccessToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const response = await fetch(`${BASE}/support/${ticket.id}/screenshot`, {
        headers,
        credentials: 'include',
    });
    if (!response.ok) throw new Error('Could not download screenshot');
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = ticket.screenshot_name || `support-${ticket.id}-screenshot`;
    anchor.click();
    URL.revokeObjectURL(url);
}
