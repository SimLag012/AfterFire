import logging
from typing import Dict, Any, List, Optional
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class AIAnalyst:
    """
    Scientific AI Analyst for AfterFire.
    Operates in two modes:
    1. Deterministic Scientific Explainer (Default, 100% reproducible, zero external dependency)
    2. Fact-Grounded LLM Explainer (Optional, enabled when LLM_API_KEY is configured)
    
    Strict constraints:
    - Grounded strictly on backend calculated metrics.
    - Explicitly separates observations from mathematical results and ecological hypotheses.
    - Never hallucinates figures, dates, or non-existent satellite passes.
    """

    @classmethod
    async def explain(
        cls, 
        area_name: str, 
        focus_topic: str, 
        metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generates scientific explanation based on structured metrics."""
        if settings.LLM_API_KEY and settings.LLM_API_KEY.strip():
            try:
                return await cls._query_llm_analyst(area_name, focus_topic, metrics)
            except Exception as e:
                logger.warning(f"LLM call failed ({e}); falling back to deterministic explainer.")

        return cls._generate_deterministic_explanation(area_name, focus_topic, metrics)

    @classmethod
    def _generate_deterministic_explanation(
        cls, 
        area_name: str, 
        focus_topic: str, 
        m: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generates robust, transparent, scientific synthesis without hallucination."""
        total_dets = m.get("total_detections", 0)
        modis_dets = m.get("modis_detections", 0)
        viirs_dets = m.get("viirs_detections", 0)
        burned_ha = m.get("burned_area_hectares")
        rec_status = m.get("recovery_status", "Evaluation pending")
        drop_pct = m.get("drop_pct", 0.0)
        recovery_pct = m.get("recovery_pct", 0.0)
        baseline = m.get("pre_fire_baseline_mean", 0.0)
        trough = m.get("fire_trough_ndvi", 0.0)
        latest_ndvi = m.get("latest_ndvi", 0.0)

        findings = []
        limitations = [
            "Thermal hotspot frequency reflects satellite detection opportunities and sensor thresholds, not necessarily ground fire boundary.",
            "NDVI measures spectral chlorophyll greenness, which can rebound via early-successional scrub/grasses before forest canopy structure re-establishes.",
            "Atmospheric cloud and smoke interference can suppress valid observations during active burning phases."
        ]

        if focus_topic == "harmonization":
            summary = (
                f"Harmonized observation for '{area_name}' combines {total_dets} total thermal detections "
                f"across MODIS ({modis_dets}) and VIIRS ({viirs_dets}). "
                f"VIIRS (375m I-band) provides approximately 3-fold higher spatial resolution than MODIS (1km), "
                f"enabling detection of finer flaming fronts and cooler smoldering edges. "
                f"The detections have been harmonized into standardized confidence tiers and grouped into candidate spatiotemporal clusters."
            )
            findings.append(f"Dual-sensor integration: {modis_dets} MODIS detections vs {viirs_dets} VIIRS detections.")
            findings.append("Detections are harmonized by acquisition timestamp and geographic coordinates without double-counting physical fire extent.")
            if burned_ha:
                findings.append(f"MCD64A1 500m mapped burned area: {burned_ha:,.1f} hectares.")

        elif focus_topic == "recovery":
            summary = (
                f"Post-fire recovery analysis for '{area_name}' indicates a '{rec_status}' trajectory. "
                f"Pre-fire baseline canopy greenness averaged an NDVI of {baseline:.3f}. "
                f"Following fire disturbance, the index decreased to a minimum of {trough:.3f} (a {drop_pct:.1f}% reduction). "
                f"The latest valid composite records an NDVI of {latest_ndvi:.3f}, representing a {recovery_pct:.1f}% return toward the pre-fire baseline."
            )
            findings.append(f"Disturbance magnitude: NDVI dropped from {baseline:.3f} to {trough:.3f} (-{drop_pct:.1f}%).")
            findings.append(f"Current trajectory status: '{rec_status}' ({recovery_pct:.1f}% recovered relative to baseline).")
            findings.append(f"Latest observed composite NDVI: {latest_ndvi:.3f}.")

        elif focus_topic == "recurrence":
            events_c = m.get("events_count", 1)
            mean_ret = m.get("mean_return_interval_days")
            summary = (
                f"Disturbance chronology for '{area_name}' includes {events_c} candidate wildfire cluster(s). "
                + (f"Average return interval between successive events is {mean_ret:.0f} days ({round(mean_ret/365, 1)} years). " if mean_ret else "No prior recurring events in the analyzed timeframe. ")
                + "Multiple fires before full canopy restoration can impede mature forest succession and favor fire-adapted shrub cover."
            )
            findings.append(f"Total identified disturbance clusters: {events_c}.")
            if mean_ret:
                findings.append(f"Mean recurrence interval: {mean_ret:.0f} days.")
            findings.append("Recurrence analysis distinguishes thermal hotspot clusters from official cadastral perimeters.")

        else:  # overview
            summary = (
                f"Territory overview for '{area_name}': {total_dets} harmonized thermal anomaly detections recorded "
                f"({modis_dets} MODIS, {viirs_dets} VIIRS). "
                + (f"MCD64A1 mapped burned area covers {burned_ha:,.1f} hectares. " if burned_ha else "")
                + f"Vegetation recovery classification is '{rec_status}' based on 16-day MOD13Q1 composite time series."
            )
            findings.append(f"Total thermal detections: {total_dets} ({modis_dets} MODIS, {viirs_dets} VIIRS).")
            if burned_ha:
                findings.append(f"MCD64A1 mapped burned area: {burned_ha:,.1f} ha.")
            findings.append(f"Post-fire vegetation status: {rec_status} ({recovery_pct:.1f}% recovered).")

        return {
            "area_name": area_name,
            "focus_topic": focus_topic,
            "scientific_summary": summary,
            "key_findings": findings,
            "limitations": limitations,
            "is_llm_generated": False,
            "data_basis": m
        }

    @classmethod
    async def _query_llm_analyst(
        cls, 
        area_name: str, 
        focus_topic: str, 
        m: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calls external LLM when key is present, passing structured metrics."""
        prompt = (
            f"You are a remote-sensing scientist and geospatial analyst for the NASA Space Apps Challenge project 'AfterFire'. "
            f"Analyze the following verified satellite metrics for area '{area_name}' focusing on '{focus_topic}'. "
            f"Metrics: {m}. "
            f"Strict rules: "
            f"1. Only cite numbers provided in the metrics. "
            f"2. Separate confirmed observations from ecological hypotheses. "
            f"3. Note that NDVI represents greenness, not full biodiversity recovery. "
            f"4. Provide a concise scientific summary, 3 bullet key findings, and explicit satellite limitations."
        )
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "You are a remote-sensing scientific analyst for AfterFire. Adhere strictly to provided satellite metrics."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2
                }
            )
            if res.status_code == 200:
                data = res.json()
                content = data["choices"][0]["message"]["content"]
                return {
                    "area_name": area_name,
                    "focus_topic": focus_topic,
                    "scientific_summary": content,
                    "key_findings": [
                        f"Analysis based on {m.get('total_detections', 0)} harmonized satellite thermal detections.",
                        f"Post-fire vegetation trajectory evaluated at {m.get('recovery_pct', 0.0)}% recovery relative to baseline.",
                        "Grounded in MODIS MCD64A1, MOD13Q1, and VIIRS observations."
                    ],
                    "limitations": [
                        "Model-assisted narrative generated strictly from verified numerical satellite metrics.",
                        "NDVI canopy recovery does not equate to mature forest climax recovery."
                    ],
                    "is_llm_generated": True,
                    "data_basis": m
                }
            else:
                raise RuntimeError(f"LLM API returned status {res.status_code}")

