#!/usr/bin/env python3
"""Read-only Upbit KRW market snapshot. No credentials, trading or orders."""
import csv, datetime as dt, json, os, random, statistics, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

BASE = 'https://api.upbit.com/v1'
OUT = Path('output'); OUT.mkdir(exist_ok=True)
KST = dt.timezone(dt.timedelta(hours=9))
THEMES = {
 'AI / compute': {'RENDER','TAO','FET','AGIX','OCEAN','ARKM','IO','ATH','AKT','GRT'},
 'Layer 2': {'ARB','OP','STRK','IMX','ZK','MANTA','METIS','POL','LRC'},
 'Gaming': {'IMX','YGG','GALA','AXS','SAND','MANA','BEAM','PIXEL'},
 'DeFi': {'AAVE','UNI','CRV','COMP','SNX','KNC','LDO','PENDLE'},
 'Storage': {'FIL','AR','STORJ','SC'},
 'Meme': {'DOGE','SHIB','PEPE','BONK','FLOKI','WIF'},
 'Privacy': {'ZEN','ZEC','XMR'},
}
HOLDINGS = {}  # Keep private holdings out of a public repository

def fetch(path, params=None):
    url = BASE + path + ('?' + urllib.parse.urlencode(params, doseq=True) if params else '')
    for attempt in range(5):  # first request + up to 4 retries
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'upbit-monitor-readonly/1.0','Accept':'application/json'})
            with urllib.request.urlopen(req, timeout=12) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            if attempt == 4: raise RuntimeError(f'{path}: {type(exc).__name__}: {exc}') from exc
            time.sleep([2,5,10,20][attempt] + random.uniform(0,0.5))

def rsi(closes, n=14):
    if len(closes) < n+1: return None
    diffs=[b-a for a,b in zip(closes[:-1],closes[1:])][-n:]
    gain=sum(max(x,0) for x in diffs)/n; loss=sum(max(-x,0) for x in diffs)/n
    return 100.0 if loss == 0 else 100 - 100/(1+gain/loss)

def main():
    now=dt.datetime.now(KST)
    print('START',now.isoformat(),flush=True)
    markets=sorted(x['market'] for x in fetch('/market/all',{'isDetails':'false'}) if x['market'].startswith('KRW-'))
    tickers=[]
    for i in range(0,len(markets),50):
        tickers += fetch('/ticker', {'markets':','.join(markets[i:i+50])})
        time.sleep(0.25)
    by_market={t['market']:t for t in tickers}
    rows=[]; errors=[]
    for i,market in enumerate(markets):
        t=by_market.get(market)
        if not t: errors.append(f'{market}: missing ticker'); continue
        try:
            candles=fetch('/candles/minutes/60',{'market':market,'count':25})
            if len(candles)<16: raise ValueError('insufficient 60m candles')
            candles=list(reversed(candles))
            closes=[float(c['trade_price']) for c in candles]
            recent=candles[-1]; prev=candles[-2]
            # Latest 60-minute candle may be incomplete; compare the last COMPLETE hourly candle to previous 6.
            completed=candles[-2]; baseline=candles[-8:-2]
            vol_hour=float(completed['candle_acc_trade_price'])
            base_hour=statistics.median(float(c['candle_acc_trade_price']) for c in baseline)
            hour_ratio=vol_hour/base_hour if base_hour>0 else None
            range_=float(completed['high_price'])-float(completed['low_price'])
            close_position=(float(completed['trade_price'])-float(completed['low_price']))/range_ if range_>0 else 0.5
            code=market[4:]
            row={'market':market,'symbol':code,'price_krw':t['trade_price'],
                'change_24h_pct':round(100*float(t['signed_change_rate']),3),
                'turnover_24h_krw':round(float(t['acc_trade_price_24h'])),
                'high_24h_krw':t['high_price'],'low_24h_krw':t['low_price'],
                'last_completed_hour_turnover_krw':round(vol_hour),
                'hour_turnover_vs_prev6_median':round(hour_ratio,2) if hour_ratio is not None else None,
                'last_completed_hour_close_position':round(close_position,3),
                'last_completed_hour_green':float(completed['trade_price'])>float(completed['opening_price']),
                'last_completed_hour_end_kst':completed['candle_date_time_kst'],
                'rsi14_60m':round(rsi(closes),1) if rsi(closes) is not None else None,
                'themes':','.join(k for k,v in THEMES.items() if code in v),
                'held_avg_krw':HOLDINGS.get(code),
                'vs_held_avg_pct':round(100*(float(t['trade_price'])/HOLDINGS[code]-1),2) if code in HOLDINGS else None}
            rows.append(row)
        except (RuntimeError, ValueError, KeyError, TypeError) as exc:
            errors.append(f'{market}: {str(exc)[:160]}')
        time.sleep(0.15)  # throttle to reduce rate-limit errors
        if (i+1)%50==0: print('PROGRESS',i+1,'/',len(markets),flush=True)
    complete=len(rows)==len(markets) and not errors
    snapshot={'checked_at_kst':dt.datetime.now(KST).isoformat(timespec='seconds'),
              'markets_expected':len(markets),'markets_analyzed':len(rows),'complete':complete,
              'up':sum(r['change_24h_pct']>0 for r in rows),
              'down':sum(r['change_24h_pct']<0 for r in rows),'flat':sum(r['change_24h_pct']==0 for r in rows),
              'errors':errors[:50], 'data':rows}
    (OUT/'snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
    if rows:
        with (OUT/'markets.csv').open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    candidates=sorted((r for r in rows if 3<=r['change_24h_pct']<=12 and
        r['hour_turnover_vs_prev6_median'] is not None and r['hour_turnover_vs_prev6_median']>=1.5 and
        r['last_completed_hour_green'] and r['last_completed_hour_close_position']>=0.65 and
        r['turnover_24h_krw']>=1_000_000_000 and r['rsi14_60m'] is not None and r['rsi14_60m']<70),
        key=lambda r:(r['hour_turnover_vs_prev6_median'],r['turnover_24h_krw']),reverse=True)
    lines=['# Upbit KRW monitoring — observation only', '',f"- Checked KST: {snapshot['checked_at_kst']}",
           f"- Coverage: {len(rows)}/{len(markets)} markets; complete={complete}",
           f"- Breadth (analyzed only): up {snapshot['up']}, down {snapshot['down']}, flat {snapshot['flat']}",
           '- All prices and volumes from Upbit public API only; 60-minute candle volume is from the last completed candle.',
           '- Screening is **NOT an A/B+ trade signal**. Theme leadership, risk/reward, support, execution and cross-checks need human review.',
           '- No trading, orders, wallets, secrets or account access.','', '## Observation shortlist',
           '| Market | Price KRW | 24h % | 24h turnover KRW | Hour volume ratio | RSI14 | Themes |',
           '|---|---:|---:|---:|---:|---:|---|']
    for r in candidates[:20]:
        lines.append(f"| {r['market']} | {r['price_krw']} | {r['change_24h_pct']} | {r['turnover_24h_krw']:,} | {r['hour_turnover_vs_prev6_median']} | {r['rsi14_60m']} | {r['themes']} |")
    lines += ['', '## Previously reported holdings (not account-verified)',
              '| Market | Last price KRW | Reported average KRW | Change vs avg % |', '|---|---:|---:|---:|']
    for r in rows:
        if r['held_avg_krw'] is not None:
            lines.append(f"| {r['market']} | {r['price_krw']} | {r['held_avg_krw']} | {r['vs_held_avg_pct']} |")
    if errors: lines+=['','## Data gaps']+[f'- {e}' for e in errors[:15]]
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('END',snapshot['checked_at_kst'],'coverage',len(rows),'/',len(markets),'candidates',len(candidates),flush=True)
    if not complete: raise SystemExit('Incomplete market coverage: do not issue trade alerts')

if __name__=='__main__': main()
