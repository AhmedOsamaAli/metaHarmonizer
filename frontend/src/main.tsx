import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { AuthProvider } from './context/AuthContext';
import { JobsProvider } from './context/JobsContext';
import { NotificationsProvider } from './context/NotificationsContext';
import { ThemeProvider } from './context/ThemeContext';
import { TourProvider } from './components/Walkthrough';
import './index.css';

// Apply the saved theme before first paint. Bundled (served from 'self'),
// so it satisfies the CSP that blocks inline <script> in index.html.
try {
  const saved = localStorage.getItem('theme');
  const dark = saved === 'dark';
  document.documentElement.classList.toggle('dark', dark);
} catch {
  /* ignore */
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider>
          <AuthProvider>
            <NotificationsProvider>
              <JobsProvider>
                <TourProvider>
                  <App />
                </TourProvider>
              </JobsProvider>
            </NotificationsProvider>
          </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
