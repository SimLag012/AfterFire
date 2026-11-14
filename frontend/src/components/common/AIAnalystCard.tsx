import React, { useState } from 'react';
import { ExplainResponse } from '../../types';
import { apiClient } from '../../api/client';

interface AIAnalystCardProps {
  areaId: string;
  areaName: string;
  initialExplanation?: ExplainResponse;
}

const topics = {
  overview: 'Overview',
  recovery: 'Recovery',
  harmonization: 'Sensor alignment',
  recurrence: 'Recurrence',
} as const;

type Topic = keyof typeof topics;

export const AIAnalystCard: React.FC<AIAnalystCardProps> = ({ areaId, areaName, initialExplanation }) => {
  const [topic, setTopic] = useState<Topic>('overview');
  const [explanation, setExplanation] = useState(initialExplanation);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  const fetchExplanation = async (newTopic: Topic) => {
    setLoading(true);
    setFailed(false);
    setTopic(newTopic);
    try {
      setExplanation(await apiClient.explainArea(areaId, newTopic));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="observation-notes" aria-labelledby="observation-notes-title">
      <header>
        <h2 id="observation-notes-title">Observation notes</h2>
        {explanation && !loading && !failed && (
          <p className="text-sm text-slate-400">{explanation.is_llm_generated
            ? 'Generated with a language model using the calculated metrics.'
            : 'Summary calculated from the observation metrics.'}</p>
        )}
      </header>
      <div className="observation-topics" role="group" aria-label="Explanation topic">
        {(Object.keys(topics) as Topic[]).map(option => (
          <button key={option} type="button" aria-pressed={topic === option}
            disabled={loading} onClick={() => fetchExplanation(option)}>{topics[option]}</button>
        ))}
      </div>
      {loading ? <p role="status">Preparing observation notes…</p>
        : failed ? <p role="alert">Could not load {topics[topic].toLowerCase()} notes. Select the topic again to retry.</p>
        : explanation ? (
          <div className="observation-prose">
            <p>{explanation.scientific_summary}</p>
            {!!explanation.key_findings?.length && (
              <div>
                <h3>Findings</h3>
                <ul>{explanation.key_findings.map((finding, idx) => <li key={idx}>{finding}</li>)}</ul>
              </div>
            )}
            {!!explanation.limitations?.length && (
              <details>
                <summary>Limits of the observations</summary>
                <ul>{explanation.limitations.map((limitation, idx) => <li key={idx}>{limitation}</li>)}</ul>
              </details>
            )}
          </div>
        ) : <p className="text-slate-400">Choose a topic to read about {areaName}.</p>}
    </section>
  );
};
