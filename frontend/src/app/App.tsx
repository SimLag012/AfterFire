import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navbar } from '../components/layout/Navbar';
import { Footer } from '../components/layout/Footer';
import { HomePage } from '../pages/HomePage';
import { ExplorerPage } from '../pages/ExplorerPage';
import { TerritoryPage } from '../pages/TerritoryPage';
import { RecoveryPage } from '../pages/RecoveryPage';
import { RecurrencePage } from '../pages/RecurrencePage';
import { ComparePage } from '../pages/ComparePage';
import { ReportPage } from '../pages/ReportPage';
import { DatasetsPage } from '../pages/DatasetsPage';

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
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/explorer" element={<ExplorerPage />} />
              <Route path="/territory/:areaId" element={<TerritoryPage />} />
              <Route path="/recovery/:areaId" element={<RecoveryPage />} />
              <Route path="/recurrence/:areaId" element={<RecurrencePage />} />
              <Route path="/compare" element={<ComparePage />} />
              <Route path="/report/:areaId" element={<ReportPage />} />
              <Route path="/datasets" element={<DatasetsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
          <Footer />
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

