import React, { useMemo, useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { LeafletMap } from '../components/map/LeafletMap';
import { TimelineBar, TimelinePhase } from '../components/timeline/TimelineBar';
import '../styles/field-pages.css';

const toDateValue = (date: string | undefined, fallback: string): string => {
  if (!date || Number.isNaN(new Date(`${date}T00:00:00.000Z`).getTime())) {
    return fallback;
  }
  return date;
};

const addDays = (date: string, days: number): string => {
  const timestamp = new Date(`${date}T00:00:00.000Z`).getTime() + days * 24 * 60 * 60 * 1000;
  return new Date(timestamp).toISOString().slice(0, 10);
};

export const TerritoryPage: React.FC = () => {
  const { areaId = 'rhodes-greece-2023' } = useParams<{ areaId: string }>();
  const [currentPhase, setCurrentPhase] = useState<TimelinePhase>('fire');
  const [selectedDate, setSelectedDate] = useState<string>('2023-07-22');

  // Query territory
  const { data: area, isLoading: areaLoading, isError: areaError } = useQuery({
    queryKey: ['area', areaId],
    queryFn: () => apiClient.getArea(areaId),
  });

  // Query summary
  const { data: summary } = useQuery({
    queryKey: ['areaSummary', areaId],
    queryFn: () => apiClient.getAreaSummary(areaId),
  });

  // Query candidate events
  const { data: events = [], isLoading: eventsLoading, isError: eventsError } = useQuery({
    queryKey: ['events', areaId],
    queryFn: () => apiClient.getEvents(areaId),
  });

  const firstEvent = events[0];

  // Query detections
  const { data: allDetections = [] } = useQuery({
    queryKey: ['detections', areaId],
    queryFn: () => apiClient.getDetections(areaId),
  });

  // Query burned area
  const { data: burnedSummary } = useQuery({
    queryKey: ['burnedArea', areaId],
    queryFn: () => apiClient.getBurnedArea(areaId),
  });

  const fireStartDate = toDateValue(firstEvent?.start_date, '2023-07-18');
  const fireEndDate = toDateValue(firstEvent?.end_date, '2023-07-28');
  const hasFireWindow = Boolean(firstEvent?.start_date && firstEvent?.end_date);
  const beforeDate = addDays(fireStartDate, -30);
  const afterDate = addDays(fireEndDate, 18);
  const recoveryDate = addDays(fireEndDate, 320);

  useEffect(() => {
    if (!firstEvent) return;
    setSelectedDate(fireStartDate);
  }, [firstEvent?.start_date]);

  const minDate = useMemo(() => addDays(fireStartDate, -365), [fireStartDate]);
  const maxDate = useMemo(() => addDays(recoveryDate, 120), [recoveryDate]);

  const resolvedDate = selectedDate || fireStartDate;

  const phaseDateMap: Record<TimelinePhase, string> = {
    before: beforeDate,
    fire: fireStartDate,
    after: afterDate,
    recovery: recoveryDate,
  };

  const mapContextDate = toDateValue(resolvedDate, fireStartDate);

  const displayedDetections = currentPhase === 'fire' ? allDetections.filter(detection =>
    detection.acq_date && detection.acq_date >= fireStartDate && detection.acq_date <= fireEndDate,
  ) : [];
  const visibleLayers = {
    modis: currentPhase === 'fire',
    viirs: currentPhase === 'fire',
    burnedArea: currentPhase === 'after' || currentPhase === 'recovery',
    satelliteContext: true,
  };
  const phases = {
    before: { title: 'Before the fire', description: 'Satellite imagery provides context for the territory before the selected fire window.' },
    fire: { title: 'Fire observations', description: 'The map displays MODIS and VIIRS thermal detections inside the fire date window.' },
    after: { title: 'After the fire', description: 'MCD64A1 mapped burned area is shown where observations are available.' },
    recovery: { title: 'Vegetation after fire', description: 'Open the vegetation report for the MOD13Q1 time series and quality-screened observations.' },
  };
  const activePhase = phases[currentPhase];

  return (
    <main className="field-page">
      <header className="field-header split">
        <div>
          <Link to="/explorer" className="field-link">Fire map</Link>
          <h1>{area?.name || 'Territory story'}</h1>
          {area && <p className="field-data">{area.min_lat.toFixed(2)}° to {area.max_lat.toFixed(2)}° latitude, {area.min_lon.toFixed(2)}° to {area.max_lon.toFixed(2)}° longitude ({area.area_km2.toFixed(0)} km²)</p>}
        </div>
        <Link to={`/recovery/${areaId}`} className="field-button primary">Open vegetation report</Link>
      </header>
      {areaLoading && <p role="status" className="field-quiet">Loading territory…</p>}
      {areaError && <p role="alert" className="field-note">Territory details are unavailable. Return to the fire map to select another area.</p>}
      {area?.is_demo_preset === 'true' && <p role="note" className="field-note">Historical synthetic study area</p>}
      {area && !hasFireWindow && (
        eventsLoading ? <p role="status" className="field-quiet">Loading the territory’s fire window…</p>
          : eventsError ? <p role="alert" className="field-note">The territory’s fire window is unavailable. Retry or return to the fire map.</p>
            : <p className="field-note">No fire window has been recorded for this territory. Open the fire map to search by location and date.</p>
      )}
      {hasFireWindow && <section className="field-section" aria-labelledby="territory-observations">
        <h2 id="territory-observations">Territory observations</h2>
        <TimelineBar
          currentPhase={currentPhase}
          onPhaseChange={(p) => {
            setCurrentPhase(p);
            setSelectedDate(phaseDateMap[p] ?? mapContextDate);
          }}
          currentDate={mapContextDate}
          onDateChange={(date) => {
            setSelectedDate(date);
            const time = new Date(`${date}T00:00:00.000Z`).getTime();
            if (time < new Date(`${fireStartDate}T00:00:00.000Z`).getTime()) {
              setCurrentPhase('before');
            } else if (time <= new Date(`${fireEndDate}T00:00:00.000Z`).getTime()) {
              setCurrentPhase('fire');
            } else if (time <= new Date(`${afterDate}T00:00:00.000Z`).getTime()) {
              setCurrentPhase('after');
            } else {
              setCurrentPhase('recovery');
            }
          }}
          minimumDate={minDate}
          maximumDate={maxDate}
          fireStartDate={fireStartDate}
          fireEndDate={fireEndDate}
        />
        <div className="field-territory">
          <div className="field-map" aria-label="Territory observation map">
            <LeafletMap
              area={area}
              detections={displayedDetections}
              burnedArea={burnedSummary?.observations || []}
              visibleLayers={visibleLayers}
              contextDate={mapContextDate}
            />
          </div>
          <div className="field-section">
            <header>
              <h3>{activePhase.title}</h3>
              <p>{activePhase.description}</p>
            </header>
            <dl className="field-measures">
              <div><dt>Requested imagery date (UTC)</dt><dd className="field-data">{mapContextDate}</dd></div>
              {currentPhase === 'fire' && (
                <div><dt>Thermal detections</dt><dd className="field-data">{displayedDetections.length.toLocaleString()}</dd></div>
              )}
              {currentPhase === 'fire' && firstEvent?.max_frp_mw != null && (
                <div><dt>Maximum fire radiative power</dt><dd className="field-data">{firstEvent.max_frp_mw.toLocaleString()} MW</dd></div>
              )}
              {visibleLayers.burnedArea && (
                <div><dt>Mapped burned area</dt><dd className="field-data">{summary?.total_burned_area_hectares != null ? `${summary.total_burned_area_hectares.toLocaleString()} ha` : 'Unavailable'}</dd></div>
              )}
            </dl>
          </div>
        </div>
      </section>}

      <section className="field-section" aria-labelledby="territory-sources">
        <h2 id="territory-sources">Satellite products</h2>
        <dl className="field-register">
          <div className="field-row"><dt>MODIS and VIIRS</dt><dd>Harmonization preserves instrument identity for MODIS (1 km) and VIIRS (375 m) thermal detections.</dd></div>
          <div className="field-row"><dt>MCD64A1</dt><dd>The global monthly 500 m burned-area product shows mapped surface change. Thermal detections indicate active heat.</dd></div>
          <div className="field-row"><dt>MOD13Q1</dt><dd>The 16-day, 250 m vegetation series masks observations affected by snow, cloud and heavy aerosol.</dd></div>
        </dl>
      </section>
    </main>
  );
};
