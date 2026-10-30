import React, { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navbar } from '../components/layout/Navbar';
import { Footer } from '../components/layout/Footer';
const HomePage = lazy(() => import('../pages/HomePage').then(m => ({default: m.HomePage})));
const ExplorerPage = lazy(() => import('../pages/ExplorerPage').then(m => ({default: m.ExplorerPage})));
const TerritoryPage = lazy(() => import('../pages/TerritoryPage').then(m => ({default: m.TerritoryPage})));
const RecoveryPage = lazy(() => import('../pages/RecoveryPage').then(m => ({default: m.RecoveryPage})));
const RecurrencePage = lazy(() => import('../pages/RecurrencePage').then(m => ({default: m.RecurrencePage})));
const ComparePage = lazy(() => import('../pages/ComparePage').then(m => ({default: m.ComparePage})));
const ReportPage = lazy(() => import('../pages/ReportPage').then(m => ({default: m.ReportPage})));
const DatasetsPage = lazy(() => import('../pages/DatasetsPage').then(m => ({default: m.DatasetsPage})));
const EventAnalysisPage = lazy(() => import('../pages/EventAnalysisPage').then(m => ({default: m.EventAnalysisPage})));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 1000 * 60 * 5, // 5 minutes cache
      retry: 1,
    },
  },
});

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen flex flex-col bg-dark-950 text-slate-100 font-sans selection:bg-accent-fire/30 selection:text-white">
          <Navbar />
          <div className="flex-1">
            <Suspense fallback={<p role="status" aria-live="polite" className="p-8">Loading page…</p>}><Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/explorer" element={<ExplorerPage />} />
              <Route path="/events/:eventId" element={<EventAnalysisPage />} />
              <Route path="/territory/:areaId" element={<TerritoryPage />} />
              <Route path="/recovery/:areaId" element={<RecoveryPage />} />
              <Route path="/recurrence" element={<RecurrencePage />} />
              <Route path="/events/:eventId/reburn" element={<RecurrencePage />} />
              <Route path="/recurrence/:areaId" element={<RecurrencePage />} />
              <Route path="/compare" element={<ComparePage />} />
              <Route path="/report/:areaId" element={<ReportPage />} />
              <Route path="/datasets" element={<DatasetsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes></Suspense>
          </div>
          <Footer />
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
};
