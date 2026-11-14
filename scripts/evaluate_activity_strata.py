"""Exploratory calendar-stratum fits from retained authentic NASA samples only.

Keeps the original training/interval/geographic/temporal folds and all numeric
acceptance gates. This experiment follows the pooled test result: its holdouts
are reused, so it is NOT an independent confirmatory model release. No NASA
requests, database writes, or production artifact installation.
"""
import argparse
import json
from pathlib import Path
from app.fire_activity.science import fit
from validate_activity_seasons import evaluate_seasons


def main(args):
    samples=json.loads(args.samples.read_text())
    output={'scope':__doc__,'strata':[]}
    for months in ([12,1,2],[3,4,5],[6,7,8],[9,10,11]):
        rows=[s for s in samples if s['month'] in months]
        model=evaluate_seasons(rows,fit(rows))
        output['strata'].append({'calendar_months':months,'sample_n':len(rows),'candidate':model,
            'release_status':'exploratory_only_requires_new_confirmatory_holdout'})
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    print(json.dumps([{'months':s['calendar_months'],'status':s['candidate']['status'],
        'passing_months':s['candidate'].get('domain_calendar_months',[])} for s in output['strata']]))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args())
