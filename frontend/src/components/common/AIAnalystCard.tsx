import React, { useState } from 'react';
import { Bot, Sparkles, CheckCircle2, AlertTriangle, Cpu, RefreshCw } from 'lucide-react';
import { ExplainResponse } from '../../types';
import { apiClient } from '../../api/client';

interface AIAnalystCardProps {
  areaId: string;
  areaName: string;
  initialExplanation?: ExplainResponse;
}

export const AIAnalystCard: React.FC<AIAnalystCardProps> = ({
  areaId,
  areaName,
  initialExplanation,
}) => {
  const [topic, setTopic] = useState<'overview' | 'recovery' | 'harmonization' | 'recurrence'>('overview');
  const [explanation, setExplanation] = useState<ExplainResponse | undefined>(initialExplanation);
  const [loading, setLoading] = useState(false);

  const fetchExplanation = async (newTopic: 'overview' | 'recovery' | 'harmonization' | 'recurrence') => {
    setLoading(true);
    setTopic(newTopic);
    try {
      const res = await apiClient.explainArea(areaId, newTopic);
      setExplanation(res);
    } catch (e) {
      console.error('Failed to fetch explanation', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-panel p-5 rounded-xl border border-dark-700/80 shadow-2xl space-y-4">
      {/* Card Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-dark-800 pb-3">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-bold text-white tracking-wide">Scientific AI Analyst</h3>
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                explanation?.is_llm_generated
                  ? 'bg-purple-500/10 text-purple-300 border-purple-500/30'
                  : 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
              }`}>
                {explanation?.is_llm_generated ? 'Fact-Grounded LLM' : 'Deterministic Metric Synthesizer'}
              </span>
            </div>
            <p className="text-xs text-slate-400">Strictly grounded in verified satellite observations</p>
          </div>
        </div>

        {/* Topic Selector Tabs */}
        <div className="flex items-center space-x-1 bg-dark-900 p-1 rounded-lg border border-dark-800 text-xs">
          {(['overview', 'recovery', 'harmonization', 'recurrence'] as const).map((t) => (
            <button
              key={t}
              onClick={() => fetchExplanation(t)}
              className={`px-2.5 py-1 rounded-md capitalize font-medium transition-colors ${
                topic === t
                  ? 'bg-dark-800 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Content Body */}
      {loading ? (
        <div className="py-8 flex items-center justify-center space-x-2 text-slate-400 text-xs">
          <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
          <span>Synthesizing remote-sensing metrics...</span>
        </div>
      ) : explanation ? (
        <div className="space-y-3.5">
          {/* Scientific Summary */}
          <div className="text-xs leading-relaxed text-slate-200 bg-dark-900/60 p-3.5 rounded-lg border border-dark-800/80">
            {explanation.scientific_summary}
          </div>

          {/* Key Findings List */}
          {explanation.key_findings && explanation.key_findings.length > 0 && (
            <div className="space-y-1.5">
              <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Key Verified Findings:</h4>
              <ul className="space-y-1">
                {explanation.key_findings.map((item, idx) => (
                  <li key={idx} className="flex items-start space-x-2 text-xs text-slate-300">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 mt-0.5" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Explicit Limitations Box */}
          {explanation.limitations && explanation.limitations.length > 0 && (
            <div className="bg-amber-500/5 border border-amber-500/20 p-3 rounded-lg text-xs space-y-1">
              <div className="flex items-center space-x-1.5 text-amber-400 font-semibold text-[11px]">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>Remote-Sensing Methodological Limitations:</span>
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-slate-400 text-[11px]">
                {explanation.limitations.map((lim, idx) => (
                  <li key={idx}>{lim}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <div className="py-6 text-center text-xs text-slate-500">
          Click a topic to generate a scientific synthesis for {areaName}.
        </div>
      )}
    </div>
  );
};

