export function candles(raw, now=Date.now()) {
  if (!Array.isArray(raw)) throw Error('일봉 응답 형식 오류');
  const rows=raw.map(r=>({time:Number(r[0]),low:Number(r[1]),high:Number(r[2]),open:Number(r[3]),close:Number(r[4]),volume:Number(r[5])}));
  if(rows.some(r=>!Object.values(r).every(Number.isFinite)||r.time<=0||r.low<=0||r.high<Math.max(r.open,r.close,r.low)||r.low>Math.min(r.open,r.close)||r.volume<0)) throw Error('유효하지 않은 OHLCV 데이터');
  return [...new Map(rows.filter(r=>(r.time+86400)*1000<=now).map(r=>[r.time,r])).values()].sort((a,b)=>a.time-b.time);
}
export function analyze(rows,now=Date.now()) {
  if(rows.length<201) throw Error('완성된 일봉 201개 이상이 필요합니다');
  if(rows.some((r,i)=>i&&r.time-rows[i-1].time!==86400)) throw Error('일봉 누락 또는 중복: 연속 일봉이 필요합니다');
  const c=rows.map(r=>r.close), n=c.length, last=c[n-1];
  const sma=p=>c.slice(-p).reduce((a,b)=>a+b,0)/p;
  let g=0,l=0; for(let i=1;i<=14;i++){const d=c[i]-c[i-1];g+=Math.max(d,0)/14;l+=Math.max(-d,0)/14;}
  for(let i=15;i<n;i++){const d=c[i]-c[i-1];g=(g*13+Math.max(d,0))/14;l=(l*13+Math.max(-d,0))/14;}
  let atr=0; for(let i=1;i<n;i++){const r=rows[i], tr=Math.max(r.high-r.low,Math.abs(r.high-c[i-1]),Math.abs(r.low-c[i-1]));if(i<=14)atr+=tr/14;else atr=(atr*13+tr)/14;}
  const stale=now-(rows[n-1].time+86400)*1000>36*3600000;
  const rsi=g===0&&l===0?50:l===0?100:100-100/(1+g/l), ma20=sma(20),ma50=sma(50),ma200=sma(200);
  const trend=last>ma200&&ma50>ma200?'상승 추세':last<ma200&&ma50<ma200?'하락 추세':'전환 구간';
  const signal=stale?'데이터 지연 · 판단 보류':trend==='상승 추세'&&last>ma20&&rsi>=45&&rsi<=70?'분할 진입 검토':trend==='하락 추세'?'노출 축소 검토':'관망 · 조건 확인';
  return {last,ma20,ma50,ma200,rsi,atr,stale,trend,signal,change:(last/c[n-2]-1)*100,support:Math.min(...rows.slice(-20).map(r=>r.low)),resistance:Math.max(...rows.slice(-20).map(r=>r.high))};
}
export function position({capital,risk,entry,stop,allocation,fee}) {
  if(![capital,risk,entry,stop,allocation,fee].every(Number.isFinite)||capital<=0||risk<=0||risk>5||entry<=0||stop<=0||stop>=entry||allocation<=0||allocation>100||fee<0||fee>5)throw Error('자본·위험 한도·진입가를 확인하세요. 손절가는 진입가보다 낮아야 합니다.');
  const budget=capital*risk/100,perUnit=entry-stop+(entry+stop)*fee/100;
  const qty=Math.min(budget/perUnit,capital*allocation/100/(entry*(1+fee/100)));
  return {qty,cost:qty*entry,loss:qty*perUnit,target:entry+2*(entry-stop),budget};
}
export function nav({eth,btc,cash,other,claims,shares,ethPrice,btcPrice,stock}) {
  const vals=[eth,btc,cash,other,claims,shares,ethPrice,btcPrice,stock];
  if(!vals.every(Number.isFinite)||vals.some(v=>v<0)||shares<=0||ethPrice<=0||btcPrice<=0||stock<=0)throw Error('모든 값을 입력하세요. 주식 수와 가격은 0보다 커야 합니다.');
  const assets=eth*ethPrice+btc*btcPrice+cash+other, common=assets-claims;
  if(common<=0)throw Error('보통주 귀속 순자산이 0 이하입니다');
  return {assets,common,perShare:common/shares,multiple:stock*shares/common,ethPerShare:eth/shares};
}
