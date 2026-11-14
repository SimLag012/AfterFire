import React from 'react';
import { RecoveryComparisonPanel } from '../components/analysis/RecoveryComparisonPanel';
import '../styles/field-pages.css';

export const ComparePage: React.FC = () => (
  <main className="field-page">
    <header className="field-header">
      <div>
        <h1>Compare post-fire vegetation evidence</h1>
        <p>Compare seasonal anomalies for two events over the same interval after the fire, each against its own local reference.</p>
      </div>
    </header>
    <RecoveryComparisonPanel />
    <p className="field-quiet">Similar greenness does not establish full ecosystem recovery.</p>
  </main>
);
