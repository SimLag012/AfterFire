import math
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from collections import defaultdict, deque

import numpy as np
from app.analysis.longitude import longitude_summary

from app.services.candidate_places import place_reference


class HarmonizationEngine:
    """
    Engine for harmonizing NASA MODIS and VIIRS Hot Spot detections.
    Addresses NASA Space Apps Challenge 2026: Harmonization of MODIS and VIIRS Hot Spots.
    
    Scientific Principles:
    1. MODIS (1km resolution nadir) and VIIRS (375m resolution nadir) have distinct spatial and radiant sensitivities.
    2. VIIRS detects smaller and cooler sub-pixel fires; raw detection counts are NOT directly additive.
    3. Retains full sensor provenance, original confidence, and raw band readings.
    4. Provides unified spatiotemporal clustering for candidate event inference.
    """

    @staticmethod
    def aggregate_calendar(
        detections: List[Dict[str, Any]], 
        granularity: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        Groups detections by temporal bucket (day, week, month, year) with full sensor breakout.
        """
        buckets = defaultdict(lambda: {
            "total_detections": 0,
            "modis_count": 0,
            "viirs_count": 0,
            "frp_values": [],
            "day_count": 0,
            "night_count": 0,
            "high_confidence_count": 0,
            "nominal_confidence_count": 0,
            "low_confidence_count": 0,
        })

        for det in detections:
            acq_d = det["acq_date"]
            if isinstance(acq_d, str):
                d_obj = datetime.strptime(acq_d[:10], "%Y-%m-%d").date()
            else:
                d_obj = acq_d

            if granularity == "day":
                key = d_obj.strftime("%Y-%m-%d")
            elif granularity == "week":
                # Start of week (Monday)
                start_w = d_obj - timedelta(days=d_obj.weekday())
                key = start_w.strftime("%Y-%m-%d")
            elif granularity == "month":
                key = d_obj.strftime("%Y-%m-01")
            elif granularity == "year":
                key = d_obj.strftime("%Y-01-01")
            else:
                key = d_obj.strftime("%Y-%m-%d")

            b = buckets[key]
            b["total_detections"] += 1
            
            inst = str(det.get("instrument", "")).upper()
            if "MODIS" in inst:
                b["modis_count"] += 1
            elif "VIIRS" in inst:
                b["viirs_count"] += 1
            else:
                b["modis_count"] += 1

            frp = det.get("frp")
            if frp is not None and frp > 0:
                b["frp_values"].append(float(frp))

            dn = str(det.get("daynight", "")).upper()
            if dn == "D":
                b["day_count"] += 1
            elif dn == "N":
                b["night_count"] += 1

            conf_lvl = str(det.get("confidence_level", "nominal")).lower()
            if conf_lvl == "high":
                b["high_confidence_count"] += 1
            elif conf_lvl == "nominal":
                b["nominal_confidence_count"] += 1
            else:
                b["low_confidence_count"] += 1

        result = []
        for key in sorted(buckets.keys()):
            data = buckets[key]
            frps = data["frp_values"]
            mean_frp = round(float(np.mean(frps)), 2) if frps else None
            max_frp = round(float(np.max(frps)), 2) if frps else None

            result.append({
                "date": key,
                "total_detections": data["total_detections"],
                "modis_count": data["modis_count"],
                "viirs_count": data["viirs_count"],
                "mean_frp": mean_frp,
                "max_frp": max_frp,
                "day_count": data["day_count"],
                "night_count": data["night_count"],
                "high_confidence_count": data["high_confidence_count"],
                "nominal_confidence_count": data["nominal_confidence_count"],
                "low_confidence_count": data["low_confidence_count"],
            })

        return result

    @staticmethod
    def cluster_candidate_events(
        area_id: str,
        detections: List[Dict[str, Any]], 
        max_distance_km: float = 7.0, 
        max_time_gap_days: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Infers candidate fire events from harmonized hotspot detections using spatiotemporal proximity.
        Explicitly flagged as an algorithmic candidate, not ground-truth perimeter.
        """
        if not detections:
            return []

        sorted_dets = sorted(
            detections, 
            key=lambda d: (
                d["acq_date"] if isinstance(d["acq_date"], date) else datetime.strptime(str(d["acq_date"])[:10], "%Y-%m-%d").date(),
                str(d.get("id", "")),
                float(d["latitude"]),
                float(d["longitude"]),
            )
        )

        clusters: List[List[Dict[str, Any]]] = []

        def haversine_km(lat1, lon1, lat2, lon2):
            R = 6371.0
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
            return 2 * R * math.asin(math.sqrt(a))

        # Spatial buckets retain only the last 15, temporally eligible points per cluster.
        # This preserves the existing greedy grouping rule without scanning every past event.
        buckets = defaultdict(deque)
        def cell(lat, lon):
            lat, lon = math.radians(lat), math.radians(lon)
            return tuple(math.floor(v / max_distance_km) for v in (
                6371 * math.cos(lat) * math.cos(lon),
                6371 * math.cos(lat) * math.sin(lon), 6371 * math.sin(lat)))
        for det in sorted_dets:
            det_date = det["acq_date"] if isinstance(det["acq_date"], date) else date.fromisoformat(str(det["acq_date"])[:10])
            lat, lon = det["latitude"], det["longitude"]
            key = cell(lat, lon)
            possible = set()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        neighbor = (key[0]+dx, key[1]+dy, key[2]+dz)
                        bucket = buckets.get(neighbor)
                        if not bucket:
                            continue
                        while bucket and (bucket[0][2] < det_date - timedelta(days=max_time_gap_days)):
                            bucket.popleft()
                        bucket = deque(p for p in bucket if p[1] >= len(clusters[p[0]]) - 15)
                        buckets[neighbor] = bucket
                        for cluster_id, point_index, point_date, plat, plon in bucket:
                            if haversine_km(lat, lon, plat, plon) <= max_distance_km:
                                possible.add(cluster_id)
            if possible:
                cluster_id = min(possible)
                clusters[cluster_id].append(det)
            else:
                cluster_id = len(clusters)
                clusters.append([det])
            buckets[key].append((cluster_id, len(clusters[cluster_id])-1, det_date, lat, lon))

        # Filter clusters with at least 3 detections to eliminate isolated sensor noise
        events = []
        for cluster in clusters:
            if len(cluster) < 3:
                continue

            dates = [
                d["acq_date"] if isinstance(d["acq_date"], date) else datetime.strptime(str(d["acq_date"])[:10], "%Y-%m-%d").date()
                for d in cluster
            ]
            start_d = min(dates)
            end_d = max(dates)
            duration = max(1, (end_d - start_d).days + 1)

            modis_c = sum(1 for d in cluster if "MODIS" in str(d.get("instrument", "")).upper())
            viirs_c = sum(1 for d in cluster if "VIIRS" in str(d.get("instrument", "")).upper())

            frps = [float(d["frp"]) for d in cluster if d.get("frp") is not None]
            tot_frp = round(float(np.sum(frps)), 1) if frps else None
            max_frp = round(float(np.max(frps)), 1) if frps else None

            # Estimate approximate spatial extent box
            lats = [d["latitude"] for d in cluster]
            lons = [d["longitude"] for d in cluster]
            min_lt, max_lt = min(lats), max(lats)
            center_lon, min_ln, max_ln, longitude_width = longitude_summary(lons)
            
            # Approximate bounding box area in km2
            lat_dist = (max_lt - min_lt) * 111.0
            lon_dist = longitude_width * 111.0 * math.cos(math.radians(np.mean(lats)))
            extent_km2 = round(max(0.5, lat_dist * lon_dist), 2)

            detection_ids = sorted(str(d.get("id") or (
                f"{d['acq_date']}:{d['latitude']:.6f}:{d['longitude']:.6f}:"
                f"{d.get('instrument', '')}:{d.get('satellite', '')}"
            )) for d in cluster)
            identity = hashlib.sha256(
                f"{area_id}:{'|'.join(detection_ids)}".encode("utf-8")
            ).hexdigest()[:32]
            event_id = f"event-{identity}"
            event_name = f"Candidate activity {start_d.strftime('%b %Y')} ({duration}d, {len(cluster)} pts)"

            events.append({
                "id": event_id,
                "area_id": area_id,
                "detection_ids": detection_ids,
                "center_lat": round(float(np.mean(lats)), 6),
                "center_lon": round(center_lon, 6),
                "min_lat": min_lt,
                "max_lat": max_lt,
                "min_lon": min_ln,
                "max_lon": max_ln,
                "name": event_name,
                "place": place_reference(float(np.mean(lats)), center_lon),
                "start_date": start_d.strftime("%Y-%m-%d"),
                "end_date": end_d.strftime("%Y-%m-%d"),
                "duration_days": duration,
                "detection_count": len(cluster),
                "modis_detections": modis_c,
                "viirs_detections": viirs_c,
                "total_frp_mw": tot_frp,
                "max_frp_mw": max_frp,
                "clustering_method": f"Greedy spatiotemporal proximity ({max_distance_km}km, max {max_time_gap_days}d gap)",
                "estimated_fire_extent_km2": extent_km2,
                "confidence_summary": f"Dual-sensor observations ({modis_c} MODIS, {viirs_c} VIIRS)" if (modis_c > 0 and viirs_c > 0) else f"Single-sensor concentrated ({len(cluster)} hits)",
                "notes": "Candidate event derived from spatiotemporal thermal anomaly clusters. Not an official cadastral wildfire perimeter.",
                "is_synthetic_demo": cluster[0].get("is_synthetic_demo") or "false"
            })

        return events
