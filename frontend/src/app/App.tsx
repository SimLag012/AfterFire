import React, { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { Navbar } from '../components/layout/Navbar';
import { recoveryApi } from '../api/recovery';
import { Footer } from '../components/layout/Footer';
const HomePage = lazy(() => import('../pages/HomePage').then(m => ({default: m.HomePage})));
const ExplorerPage = lazy(() => import('../pages/ExplorerPage').then(m => ({default: m.ExplorerPage})));
const TerritoryPage = lazy(() => import('../pages/TerritoryPage').then(m => ({default: m.TerritoryPage})));
const ReportPage = lazy(() => import('../pages/ReportPage').then(m => ({default: m.ReportPage})));
const EventAnalysisPage = lazy(() => import('../pages/EventAnalysisPage').then(m => ({default: m.EventAnalysisPage})));

function LegacyExplorerRedirect({reburn=false,sources=false}:{reburn?:boolean;sources?:boolean}) {
  const location=useLocation(); const {eventId,areaId}=useParams();
  const params=new URLSearchParams(location.search);
  const requested=eventId || params.get('event') || params.get('eventId');
  const saved=params.getAll('assessment');
  const assessments=useQuery({queryKey:['legacy-assessment-links'],queryFn:()=>recoveryApi.list(''),enabled:!requested&&saved.length>0});
  const event=requested || assessments.data?.find(a=>saved.includes(a.assessment_id))?.event_id;
  if(!requested&&saved.length>0&&assessments.isPending)return <p role="status" className="p-8">Opening saved scientific comparison…</p>;
  if(areaId) params.set('area',areaId);
  if(sources) params.set('sources','on');
  if(reburn) params.set('view','reburn');
  return <Navigate replace to={(event ? '/events/'+encodeURIComponent(event) : '/explorer')+'?'+params.toString()+(reburn&&event?'#reburn':'')}/>;
}

function ContextFooter(){const {pathname}=useLocation();return pathname==='/'||pathname==='/explorer'?null:<Footer/>;}

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
        <div className="app-shell min-h-screen flex flex-col bg-dark-950 text-slate-100 font-sans">
          <div className="app-viewport">
          <Navbar />
          <div className="app-route">
            <Suspense fallback={<p role="status" aria-live="polite" className="p-8">Loading page…</p>}><Routes>
              <Route path="/" element={<ExplorerPage />} />
              <Route path="/about" element={<HomePage />} />
              <Route path="/explorer" element={<ExplorerPage />} />
              <Route path="/events/:eventId" element={<EventAnalysisPage />} />
              <Route path="/territory/:areaId" element={<TerritoryPage />} />
              <Route path="/recovery" element={<LegacyExplorerRedirect />} />
              <Route path="/recovery/:areaId" element={<LegacyExplorerRedirect />} />
              <Route path="/recurrence" element={<LegacyExplorerRedirect reburn />} />
              <Route path="/events/:eventId/reburn" element={<LegacyExplorerRedirect reburn />} />
              <Route path="/recurrence/:areaId" element={<LegacyExplorerRedirect reburn />} />
              <Route path="/compare" element={<LegacyExplorerRedirect />} />
              <Route path="/report/:areaId" element={<ReportPage />} />
              <Route path="/datasets" element={<LegacyExplorerRedirect sources />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes></Suspense>
          </div>
          </div>
          <ContextFooter />
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
};
