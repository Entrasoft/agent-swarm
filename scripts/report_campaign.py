"""Export compact evidence and figures from a completed offline campaign.

Run with matplotlib installed in a separate authoring environment. It is not a
runtime dependency. The input campaign.json and every raw run remain untouched.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('campaign',type=Path)
    parser.add_argument('--out',type=Path,default=Path('examples/offline-campaign'))
    args=parser.parse_args()
    report=json.loads((args.campaign/'campaign.json').read_text())
    args.out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for result in report['results']:
        if 'failure' in result:
            rows.append(result)
            continue
        cfg=json.loads((args.campaign/result['path']/'config.json').read_text())
        usage=result['usage']
        rows.append(dict(path=result['path'],run_id=result['run_id'],seed=cfg['seed'],
            **{k:result[k] for k in ('m','agents','condition','lower_bound','upper_bound','gap','stopping_reason',
                'decisions_completed','worker_seconds','verification_seconds','elapsed_seconds',
                'time_to_verified_optimality_seconds','invalid_claims','duplicate_candidates','artifact_reuse',
                'messages','message_bytes')},
            input_tokens=usage['input_tokens'],output_tokens=usage['output_tokens'],
            simulated_cost=usage['known_cost'],simulated_coordination_cost=usage['groups']['purpose'].get('coordination',{}).get('known_cost','0'),
            simulated_retry_cost=usage['retry_cost'],unknown_attempts=usage['unknown_attempts'],
            code_revision=cfg['code_revision'],source_sha256=cfg.get('source_sha256'),
            actual_model_calls=0,actual_model_cost='0'))
    total_tokens=sum(r.get('input_tokens',0)+r.get('output_tokens',0) for r in rows)
    spend=sum((Decimal(r.get('simulated_cost','0')) for r in rows),Decimal(0))
    coord=sum((Decimal(r.get('simulated_coordination_cost','0')) for r in rows),Decimal(0))
    retry=sum((Decimal(r.get('simulated_retry_cost','0')) for r in rows),Decimal(0))
    successes=report['totals']['successes']
    metrics=dict(total_simulated_tokens=total_tokens,total_simulated_cost=str(spend),
        simulated_cost_per_verified_solution=str(spend/successes) if successes else None,
        verified_cardinality_per_million_simulated_tokens=sum(r.get('lower_bound',0) for r in rows)*1e6/total_tokens if total_tokens else None,
        simulated_coordination_fraction=str(coord/spend) if spend else None,
        simulated_retry_fraction=str(retry/spend) if spend else None,
        definition='Initial L=0. Numerators include unsuccessful runs. All tokens and dollar rates are simulated; no LLM efficiency claim.')
    compact={k:report[k] for k in ('matrix','totals','groups','deterministic_baselines')}
    compact.update(results=rows,metrics=metrics,environment=dict(python=sys.version.split()[0],platform=platform.platform(),machine=platform.machine()),
                   raw_event_archive='events.jsonl.gz',raw_event_archive_format='One unchanged original event per line; partition by run_id.')
    with gzip.GzipFile(filename=str(args.out/'events.jsonl.gz'),mode='wb',mtime=0) as output:
        for row in rows:
            path=args.campaign/row['path']/'events.jsonl'
            if path.exists(): output.write(path.read_bytes())
    compact['raw_event_archive_sha256']=hashlib.sha256((args.out/'events.jsonl.gz').read_bytes()).hexdigest()
    (args.out/'results.json').write_text(json.dumps(compact,indent=2)+'\n')
    fields=[k for k in rows[0] if k!='source_sha256']
    with (args.out/'results.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore')
        writer.writeheader();writer.writerows(rows)
    # Public graphs are derived from actual recorded events. No invented activity.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    colors=['#334155','#0f766e','#0369a1','#7c3aed','#be123c','#b45309','#4d7c0f']
    fig,(ax,cost_ax)=plt.subplots(1,2,figsize=(12,4.8),layout='constrained',gridspec_kw={'width_ratios':[1.2,1]})
    selected=[r for r in rows if r.get('m')==24 and r.get('seed')==0]
    for index,row in enumerate(r for r in rows if r.get('m')==24 and r.get('seed')==0):
        cost=Decimal(0);gap=24;xs=[0];ys=[24]
        for line in (args.campaign/row['path']/'events.jsonl').read_text().splitlines():
            e=json.loads(line)
            if e['event_type']=='usage': cost+=Decimal(e['payload'].get('cost') or '0')
            if e['event_type']=='verification':
                # True optimum is used only for this experimenter chart, after the run.
                gap=10-e['payload']['lower_bound'];xs.append(float(cost));ys.append(gap)
        ax.step(xs[1:],ys[1:],where='post',color=colors[index],label=f"{row['condition']} N={row['agents']}")
    ax.set(title='At m=24, every condition ends one element short (seed 0)',
           xlabel='Cumulative simulated fixture cost (USD; not API spend)',ylabel='Gap to independently verified optimum 10',ylim=(0,1.5))
    ax.legend(ncols=2,fontsize=8,loc='lower right');ax.grid(alpha=.15)
    labels=[f"{r['condition']} N={r['agents']}" for r in selected]
    costs=[float(r['simulated_cost']) for r in selected]
    cost_ax.barh(labels,costs,color=colors)
    cost_ax.invert_yaxis()
    cost_ax.set(title='Final gap = 1 for all seven runs',xlabel='Total simulated fixture cost (USD)')
    cost_ax.grid(axis='x',alpha=.15)
    fig.savefig('docs/images/quality-vs-simulated-cost.png',dpi=170)
    plt.close(fig)
    row=next(r for r in rows if r.get('m')==12 and r.get('seed')==0 and r.get('agents')==10 and r.get('condition')=='adaptive')
    events=[json.loads(x) for x in (args.campaign/row['path']/'events.jsonl').read_text().splitlines()]
    from math import cos,sin,pi
    positions={f'agent-{i}':(cos(2*pi*i/10),sin(2*pi*i/10)) for i in range(10)}
    edges={}
    for e in events:
        if e['event_type']=='message_delivered':
            key=(e['actor'],e['recipient']);edges[key]=edges.get(key,0)+1
    fig,ax=plt.subplots(figsize=(8,7),layout='constrained')
    for (a,b),count in edges.items():
        ax.annotate('',xy=positions[b],xytext=positions[a],arrowprops=dict(arrowstyle='->',color='#0f766e',alpha=.35,linewidth=.6+count*.25,shrinkA=22,shrinkB=22,connectionstyle='arc3,rad=0.08'))
    for key,(x,y) in positions.items():
        coordinator=key=='agent-0'
        ax.scatter([x],[y],s=1200,color='#7c3aed' if coordinator else '#e2e8f0',edgecolor='#334155',zorder=3)
        ax.text(x,y,key.replace('agent-',''),ha='center',va='center',color='white' if coordinator else '#0f172a',fontweight='bold')
    ax.set(xlim=(-1.4,1.4),ylim=(-1.4,1.4),aspect='equal',title='Actual delivered messages · adaptive N=10 · m=12 · seed 0')
    ax.axis('off');fig.text(.5,.015,f"Node 0: assigned coordinator. {sum(edges.values())} deliveries. Programmed routing; no emergence claim.",ha='center',fontsize=9)
    fig.savefig('docs/images/actual-message-graph.png',dpi=170)
    plt.close(fig)
    print(json.dumps(metrics,indent=2))


if __name__=='__main__': main()
