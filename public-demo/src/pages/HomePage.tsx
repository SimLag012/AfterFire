import React from 'react';
import { Link } from 'react-router-dom';
import '../styles/field-pages.css';

export const HomePage: React.FC = () => {
  const presets = [
    {id:'rhodes', title:'Rhodes, Greece', date:'20–22 July 2023',
      query:'period=custom&start=2023-07-20&end=2023-07-22&sensor=MODIS&map=27.92,36.14,27.98,36.20&z=11',
      desc:'View MODIS hotspots recorded during the 2023 fire window near Rhodes.'},
    {id:'jasper', title:'Jasper, Canada', date:'23–25 July 2024',
      query:'period=custom&start=2024-07-23&end=2024-07-25&sensor=MODIS&map=-118.2,52.75,-118.0,52.95&z=10',
      desc:'Check how much seasonal reference data is available around the July 2024 fire.'},
    {id:'kangaroo', title:'Kangaroo Island, Australia', date:'2–4 January 2020',
      query:'period=custom&start=2020-01-02&end=2020-01-04&sensor=MODIS&map=136.75,-35.85,136.80,-35.80&z=11',
      desc:'Look at a small observation window around one part of the January 2020 fire.'},
  ];
  return (
    <main className="field-page">
      <header className="field-header split">
        <div>
          <h1>The life of a forest after fire</h1>
          <p>AfterFire connects MODIS and VIIRS thermal detections with satellite measurements of burned area and vegetation.</p>
        </div>
        <div className="field-actions">
          <Link to="/explorer" className="field-button primary">Open the fire map</Link>
          <Link to="/recovery" className="field-button">Browse recovery stories</Link>
        </div>
      </header>

      <section className="field-section" aria-labelledby="historical-observations">
        <header>
          <h2 id="historical-observations">Historical observation windows</h2>
          <p>Pick a location and date range to look for fire candidates on the map.</p>
        </header>
        <div className="field-register">
          {presets.map(p => (
            <article key={p.id} className="field-row">
              <div>
                <h3>{p.title}</h3>
                <p className="field-quiet"><span className="field-data">{p.date}</span></p>
              </div>
              <p>{p.desc}</p>
              <div className="field-actions">
                <Link to={`/explorer?${p.query}`} className="field-button">Explore observations<span className="sr-only"> in {p.title}</span></Link>
              </div>
            </article>
          ))}
        </div>
        <Link to="/explorer" className="field-link">Choose a different window on the map</Link>
      </section>

      <section className="field-section" aria-labelledby="observation-method">
        <h2 id="observation-method">Reading the satellite record</h2>
        <ol className="field-steps">
          <li>
            <h3>Before the fire</h3>
            <p>16-day MODIS MOD13Q1 composites provide a multi-year reference for seasonal variation in vegetation.</p>
          </li>
          <li>
            <h3>Fire disturbance</h3>
            <p>MODIS (1 km) and VIIRS (375 m) hotspots are grouped into candidates using shared confidence tiers. MCD64A1 maps burned area.</p>
          </li>
          <li>
            <h3>Vegetation after fire</h3>
            <p>NDVI and EVI are compared with seasonal references to show persistent anomalies and observation support. Burned-area records can show repeated burning.</p>
          </li>
        </ol>
      </section>

      <section className="field-section" aria-labelledby="provenance-and-limits">
        <h2 id="provenance-and-limits">Provenance and limits</h2>
        <dl className="field-register">
          <div className="field-row">
            <dt>Trace each observation</dt>
            <dd>Explorer records the acquisition date, source, satellite identity, original confidence and raw brightness where available.</dd>
          </div>
          <div className="field-row">
            <dt>Interpret vegetation indices</dt>
            <dd>Greenness can rebound as pioneer scrub grows. A spectral rebound alone cannot establish restoration of native tree canopy or biodiversity.</dd>
          </div>
          <div className="field-row">
            <dt>Reproduce the analysis</dt>
            <dd>AfterFire includes a REST API, Docker Compose setup, automated tests and client caching through TanStack Query.</dd>
          </div>
        </dl>
        <p className="field-quiet">NASA Space Apps Challenge 2026 submission for harmonization of MODIS and VIIRS hot spots.</p>
      </section>
    </main>
  );
};

