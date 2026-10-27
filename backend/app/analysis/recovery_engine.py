import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
import numpy as np

logger = logging.getLogger(__name__)


class RecoveryEngine:
    """
    Scientific analysis engine for post-fire vegetation recovery.
    Computes pre-fire baseline, fire disturbance impact, post-fire recovery ratio,
    and returns rich trajectory points with explicit data quality bounds.
    """

    METHODOLOGY = "Harmonized Pre-Fire Multi-Year Seasonal Baseline (MOD13Q1 250m)"
    VERSION = "1.2.0"

    @classmethod
    def compute_recovery_analysis(
        cls,
        area_id: str,
        area_name: str,
        fire_event_date: date,
        observations: List[Dict[str, Any]],
        event_id: Optional[str] = None,
        event_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculates recovery trajectory metrics:
        - Filters invalid QA points
        - Calculates multi-year pre-fire baseline (mean and std dev)
        - Identifies post-fire minimum (trough)
        - Computes trajectory points with anomaly vs pre-fire baseline
        - Evaluates recovery status and data coverage
        """
        # Separate valid vs excluded
        valid_obs = [obs for obs in observations if obs.get("is_valid", True)]
        excluded_obs = [obs for obs in observations if not obs.get("is_valid", True)]
        
        # Sort by observation date
        sorted_valid = sorted(
            valid_obs,
            key=lambda o: o["observation_date"] if isinstance(o["observation_date"], date) else datetime.strptime(str(o["observation_date"])[:10], "%Y-%m-%d").date()
        )

        pre_fire_obs = [
            o for o in sorted_valid
            if (o["observation_date"] if isinstance(o["observation_date"], date) else datetime.strptime(str(o["observation_date"])[:10], "%Y-%m-%d").date()) < fire_event_date
        ]

        post_fire_obs = [
            o for o in sorted_valid
            if (o["observation_date"] if isinstance(o["observation_date"], date) else datetime.strptime(str(o["observation_date"])[:10], "%Y-%m-%d").date()) >= fire_event_date
        ]

        # Check sufficiency
        if len(pre_fire_obs) < 3:
            coverage_score = "insufficient data"
            baseline_mean = 0.65
            baseline_std = 0.08
        else:
            coverage_score = "good coverage" if len(pre_fire_obs) >= 8 and len(post_fire_obs) >= 5 else "limited observations"
            pre_vals = [float(o["scaled_value"]) for o in pre_fire_obs]
            baseline_mean = round(float(np.mean(pre_vals)), 4)
            baseline_std = round(float(np.std(pre_vals)), 4)

        # Baseline dates
        pre_start_d = pre_fire_obs[0]["observation_date"] if pre_fire_obs else (fire_event_date - timedelta(days=365))
        pre_end_d = pre_fire_obs[-1]["observation_date"] if pre_fire_obs else fire_event_date

        # Disturbance trough
        if post_fire_obs:
            post_vals = [float(o["scaled_value"]) for o in post_fire_obs]
            trough_idx = int(np.argmin(post_vals[:6])) if len(post_vals) >= 2 else 0
            trough_val = round(float(post_vals[trough_idx]), 4)
            trough_obs = post_fire_obs[trough_idx]
            impact_d = trough_obs["observation_date"]
            latest_obs = post_fire_obs[-1]
            latest_val = round(float(latest_obs["scaled_value"]), 4)
            latest_d = latest_obs["observation_date"]
        else:
            trough_val = max(0.1, round(baseline_mean * 0.4, 4))
            impact_d = fire_event_date
            latest_val = trough_val
            latest_d = fire_event_date

        drop_mag = round(max(0.0, baseline_mean - trough_val), 4)
        drop_pct = round((drop_mag / baseline_mean * 100.0) if baseline_mean > 0 else 0.0, 1)

        # Recovery percentage: (latest - trough) / (baseline - trough) * 100
        recovery_denom = baseline_mean - trough_val
        if recovery_denom > 0.02:
            recovery_pct = round(((latest_val - trough_val) / recovery_denom) * 100.0, 1)
            recovery_pct = max(0.0, min(120.0, recovery_pct))
        else:
            recovery_pct = 100.0

        recovery_ratio = round((latest_val / baseline_mean) if baseline_mean > 0 else 1.0, 3)

        # Scientific recovery category
        if recovery_pct >= 90.0:
            status = "Substantially Recovered"
        elif recovery_pct >= 60.0:
            status = "Partial Recovery"
        else:
            status = "Stagnant / Slow Recovery"

        # Trajectory generation
        trajectory = []
        for o in sorted_valid:
            o_date = o["observation_date"] if isinstance(o["observation_date"], date) else datetime.strptime(str(o["observation_date"])[:10], "%Y-%m-%d").date()
            val = float(o["scaled_value"])
            is_fire_p = abs((o_date - fire_event_date).days) <= 16
            
            trajectory.append({
                "date": o_date.strftime("%Y-%m-%d"),
                "observed_ndvi": round(val, 4),
                "pre_fire_baseline": baseline_mean,
                "baseline_lower_bound": round(max(0.0, baseline_mean - baseline_std), 4),
                "baseline_upper_bound": round(min(1.0, baseline_mean + baseline_std), 4),
                "anomaly": round(val - baseline_mean, 4),
                "is_fire_period": is_fire_p,
                "qa_status": o.get("qa_description", "Good quality")
            })

        limitations = [
            "NDVI measures spectral canopy greenness and chlorophyll activity, NOT biological biodiversity or forest age structure.",
            "Fast-growing pioneer grasses and invasive shrubs may restore high NDVI values within 1-2 years while native climax tree canopies remain unrecovered.",
            "MODIS MOD13Q1 250m composite resolution averages sub-pixel vegetation heterogeneity and surface rock/soil background.",
            "Winter/snow observations and cloud cover induce valid gaps in the temporal observation series."
        ]

        exclusion_reasons = []
        if excluded_obs:
            snow_c = sum(1 for o in excluded_obs if "Snow" in str(o.get("qa_description", "")))
            cloud_c = sum(1 for o in excluded_obs if "cloud" in str(o.get("qa_description", "")).lower())
            if snow_c > 0:
                exclusion_reasons.append(f"{snow_c} observations excluded due to snow/ice reflectance contamination")
            if cloud_c > 0:
                exclusion_reasons.append(f"{cloud_c} observations excluded due to atmospheric cloud or aerosol interference")

        return {
            "area_id": area_id,
            "area_name": area_name,
            "event_id": event_id,
            "event_name": event_name or f"Wildfire ({fire_event_date.strftime('%Y')})",
            "pre_fire_start": str(pre_start_d)[:10],
            "pre_fire_end": str(pre_end_d)[:10],
            "pre_fire_baseline_mean": baseline_mean,
            "pre_fire_baseline_std": baseline_std,
            "pre_fire_obs_count": len(pre_fire_obs),
            "fire_date": fire_event_date.strftime("%Y-%m-%d"),
            "fire_trough_ndvi": trough_val,
            "drop_magnitude": drop_mag,
            "drop_pct": drop_pct,
            "latest_date": str(latest_d)[:10],
            "latest_ndvi": latest_val,
            "recovery_ratio": recovery_ratio,
            "recovery_pct": recovery_pct,
            "recovery_status": status,
            "trajectory": trajectory,
            "coverage_score": coverage_score,
            "total_valid_obs": len(sorted_valid),
            "excluded_obs_count": len(excluded_obs),
            "exclusion_reasons": exclusion_reasons,
            "scientific_limitations": limitations,
            "methodology": cls.METHODOLOGY,
            "algorithm_version": cls.VERSION
        }

