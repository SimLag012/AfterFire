import React from 'react';
import {RecoveryComparisonPanel} from '../components/analysis/RecoveryComparisonPanel';

export const ComparePage: React.FC = () => (
  <main className="mx-auto w-full max-w-7xl space-y-6 px-4 py-8 text-slate-100 sm:px-6">
    <h1 className="text-2xl font-bold">Compare post-fire vegetation evidence</h1>
    <p className="text-sm text-slate-400">Compare locally referenced seasonal anomalies over a shared post-fire interval. Similar greenness does not establish full ecosystem recovery.</p>
    <RecoveryComparisonPanel />
  </main>
);
