"""Controlled scalar/vector equivalence on deterministic native NASA pixel histories."""
import asyncio
import json
import time
import numpy as np
from datetime import date
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.models.satellite_analysis import RecoveryAssessmentRecord,EventAnalysisResult
from app.analysis.recovery_assessment import pixel_baselines,AssessmentParameters
from app.analysis.modis_science import seasonal_metrics
from app.schemas.satellite_analysis import AnalysisConfiguration

async def main():
    async with AsyncSessionLocal() as db:
        assessment=(await db.execute(select(RecoveryAssessmentRecord).where(RecoveryAssessmentRecord.event_id=='event-4a728489ea44ea85eab6a978870e0b06').order_by(RecoveryAssessmentRecord.created_at.desc()).limit(1))).scalar_one()
        source=await db.get(EventAnalysisResult,assessment.source_job_id)
    features=assessment.payload['spatial']['NDVI']['features']
    selected=np.linspace(0,len(features)-1,16,dtype=int)
    rows=sorted([o for o in source.payload['observations'] if o['index']=='NDVI'],key=lambda o:o['date'])
    matrix=np.array([[features[col]['properties']['series'][row]['value'] for col in selected] for row in range(len(rows))],dtype='float64')
    config=AnalysisConfiguration.model_validate(source.payload['configuration'])
    start,end=(date.fromisoformat(source.payload['event_period'][key]) for key in ('start','end'))
    clock=time.perf_counter()
    scalar=[]
    for col in range(matrix.shape[1]):
        series=[{**o,'value':float(matrix[row,col]) if np.isfinite(matrix[row,col]) else None} for row,o in enumerate(rows)]
        scalar.append(seasonal_metrics(series,start,end,config))
    scalar_seconds=time.perf_counter()-clock
    clock=time.perf_counter()
    baseline,band,counts,years=pixel_baselines(rows,matrix,start,config,AssessmentParameters())
    vector_seconds=time.perf_counter()-clock
    errors=[]
    for col,series in enumerate(scalar):
        for row,o in enumerate(series):
            assert counts[row,col]==o['baseline_n'] and years[row,col]==o['baseline_years']
            if o['baseline'] is None:assert np.isnan(baseline[row,col])
            else:errors.append(abs(o['baseline']-baseline[row,col]));assert abs(o['baseline_upper']-o['baseline']-band[row,col])<1e-12
    assert max(errors,default=0)<1e-12
    print(json.dumps({'source_job_id':source.job_id,'assessment_id':assessment.job_id,'index':'NDVI',
        'selected_cell_ids':[features[col]['properties']['id'] for col in selected],'cells':len(selected),'composites':len(rows),
        'scalar_seconds':scalar_seconds,'vector_seconds':vector_seconds,'max_baseline_absolute_error':max(errors,default=0),
        'counts_years_and_bands_equal':True,'benchmark_scope':'baseline calculation only; same in-memory NASA cube and parameters'},indent=2))
asyncio.run(main())
