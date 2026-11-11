#!/usr/bin/env python3
"""Read-only, conservative review of Upbit snapshot. Never emits buy/sell signals."""
import datetime as dt
import json
from pathlib import Path

KST = dt.timezone(dt.timedelta(hours=9))
OUT = Path('output')

def parse_kst(value):
    d = dt.datetime.fromisoformat(value)
    if d.tzinfo is None:
        d = d.replace(tzinfo=KST)
    return d.astimezone(KST)

def assess(snapshot, now=None):
    now = now or dt.datetime.now(KST)
    rows = snapshot.get('data', [])
    expected = snapshot.get('markets_expected', 0)
    complete = bool(snapshot.get('complete')) and expected > 0 and len(rows) == expected and not snapshot.get('errors')
    checked = parse_kst(snapshot['checked_at_kst'])
    age = (now - checked).total_seconds() / 60
    fresh = 0 <= age <= 30
    up = sum(float(r.get('change_24h_pct', 0)) > 0 for r in rows)
    down = sum(float(r.get('change_24h_pct', 0)) < 0 for r in rows)
    down_share = down / len(rows) if rows else 1
    # Broad market risk gates; never confuse these with NO TRADE based on validated price action.
    reasons = []
    if not complete: reasons.append('전체 KRW 마켓 수집 불완전')
    if not fresh: reasons.append(f'스냅샷 시각 불충분: {age:.1f}분 전')
    if down_share >= .70: reasons.append(f'시장 광범위 약세: 하락 {down_share:.1%}')
    candidates = []
    for r in rows:
        try:
            end = parse_kst(r['last_completed_hour_end_kst']) + dt.timedelta(hours=1)
            candle_age = (checked - end).total_seconds() / 60
            price = float(r['price_krw'])
            change = float(r['change_24h_pct'])
            ratio = float(r['hour_turnover_vs_prev6_median'])
            turnover = float(r['turnover_24h_krw'])
            rsi = float(r['rsi14_60m'])
            pos = float(r['last_completed_hour_close_position'])
        except (KeyError, TypeError, ValueError):
            continue
        # Candle may have no trades near the top of the hour; stale data is excluded.
        if not (-5 <= candle_age <= 75): continue
        if not (3 <= change <= 12 and ratio >= 1.8 and turnover >= 2_000_000_000): continue
        if not (rsi < 70 and pos >= .7 and r.get('last_completed_hour_green') is True): continue
        if not (price > 0 and float(r.get('low_24h_krw', 0)) > 0): continue
        candidates.append({'market': r['market'], 'price_krw': price,
            'change_24h_pct': change, 'hour_turnover_ratio': ratio,
            'turnover_24h_krw': int(turnover), 'rsi14_60m': rsi,
            'themes': r.get('themes', ''), 'completed_candle_age_min': round(candle_age, 1),
            'status': 'B 관찰 전용 (A/B+ 미확정)'})
    candidates.sort(key=lambda r: (r['hour_turnover_ratio'], r['turnover_24h_krw']), reverse=True)
    # NO_TRADE is not used: missing data and adverse market are distinct.
    status = 'DATA_UNVERIFIED' if not (complete and fresh) else ('MARKET_RISK' if down_share >= .70 else 'OBSERVATION_ONLY')
    return {'checked_at_kst': snapshot['checked_at_kst'], 'analyzed_at_kst': now.isoformat(timespec='seconds'),
        'status': status, 'coverage': f'{len(rows)}/{expected}', 'up': up, 'down': down,
        'down_share': round(down_share, 4), 'reasons': reasons, 'watchlist': candidates[:15],
        'a_or_bplus_confirmed': False, 'notification_eligible': False,
        'warning': '관찰용 스크리닝만 수행. 테마 선도주, 1/2차 진입선, 지지/손절, 목표, 손익비 검증 전에는 A/B+ 확정 불가.'}

def main():
    OUT.mkdir(exist_ok=True)
    src = OUT / 'snapshot.json'
    if not src.exists():
        result = {'status': 'DATA_UNVERIFIED', 'reasons': ['snapshot.json 없음'], 'watchlist': [],
                  'a_or_bplus_confirmed': False, 'notification_eligible': False}
    else:
        try:
            result = assess(json.loads(src.read_text(encoding='utf-8')))
        except (ValueError, KeyError, TypeError) as exc:
            result = {'status': 'DATA_UNVERIFIED', 'reasons': [f'분석 오류: {type(exc).__name__}'],
                      'watchlist': [], 'a_or_bplus_confirmed': False, 'notification_eligible': False}
    (OUT / 'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 업비트 위험 필터 / 관찰 후보 (자동매매 아님)', '', f"- 상태: **{result['status']}**",
             f"- 커버리지: {result.get('coverage', '미확인')}", '- A/B+ 확정: 없음 (미구현)',
             '- 주문·출금·API 키·자동 알림: 없음', '', '## 위험 및 보류 이유']
    lines.extend('- ' + x for x in result.get('reasons', []))
    lines += ['', '## B급 관찰 후보 (진입 권고 아님)', '|종목|가격(수집 당시)|24h %|시간 거래대금 배율|RSI|', '|---|---:|---:|---:|---:|']
    for r in result['watchlist']:
        lines.append(f"|{r['market']}|{r['price_krw']}|{r['change_24h_pct']}|{r['hour_turnover_ratio']}|{r['rsi14_60m']}|")
    (OUT / 'analysis.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('ANALYSIS', result['status'], 'watchlist', len(result['watchlist']))

if __name__ == '__main__': main()
