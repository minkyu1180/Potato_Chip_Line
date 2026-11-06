"""Station 1 material takeoff for quotations; quantities are not purchase orders."""
from __future__ import annotations

import csv
import html
import math


LABELS = {
    'square_tube': 'SUS304 사각관', 'round_tube': 'SUS304 원형관',
    'round_bar': 'SUS304 환봉', 'square_bar': 'SUS304 각봉·블록',
    'flat_bar': 'SUS304 평철', 'plate': 'SUS304 판재',
    'purchased': '구매품', 'polymer': '벨트·고무류', 'pending': '제작법·규격 확인품',
}


def rectangle_blank(points):
    """Smallest rectangle along a convex-hull edge, allowing rotation on a sheet."""
    points = sorted(set(points))
    def turn(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and turn(out[-2], out[-1], p) <= 0:
                out.pop()
            out.append(p)
        return out
    hull = half(points)[:-1] + half(reversed(points))[:-1]
    candidates = []
    for a, b in zip(hull, hull[1:]+hull[:1]):
        length = math.dist(a, b)
        ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
        x = [px*ux+py*uy for px, py in hull]
        y = [-px*uy+py*ux for px, py in hull]
        w, h = sorted((max(x)-min(x), max(y)-min(y)))
        candidates.append((w*h, w, h))
    return min(candidates)[1:]


def classify(s, c):
    """Keep stock, purchased envelopes and unresolved manufacturing routes separate."""
    n = s['name'].removeprefix('01_')
    d = s['depth']
    if 'mass_override_kg' in s:
        families = (
            ('Drum_Bearing_', '주 드럼 베어링 유닛', '축 Ø150 대응, 정격·모델 확인'),
            ('Carry_Bearing_', '지지 롤러 베어링 유닛', '축 Ø50 대응, 정격·모델 확인'),
            ('Outfeed_Bearing_', '배출 롤러 베어링 유닛', '축 Ø30 대응, 정격·모델 확인'),
            ('Outfeed_Sprocket_', '배출 스프로킷', '12개; 피치·잇수·키홈 확인'),
            ('Outfeed_Chain_', '배출 체인', '1식; 외형 길이는 체인 주문 길이가 아님'),
            ('Main_Gearbox_', '주 감속기', f"감속비 {c['gear_ratio']:g}, 토크·효율 조건 확인"),
            ('Main_Motor_', '주 모터', f"{c['motor_kw']:g} kW, 강제 냉각"),
            ('Main_Torque_Limiter_', '토크 리미터', f"설정 {c['torque_limiter_nm']:g} N·m"),
            ('Outfeed_Gearmotor_', '배출 기어모터', f"{c['outfeed_motor_kw']:g} kW, 감속비 {c['outfeed_gear_ratio']:g}"),
            ('Control_Enclosure', '제어반', '인버터 2대 포함 1식; 배선·프로그램 포함 범위 확인'),
            ('High_Level_Sensor', '레벨 센서', '1개; 식품·세척 환경 사양 확인'),
        )
        for prefix, label, note in families:
            if n.startswith(prefix):
                return dict(category='purchased', specification=label, note=note)
        raise ValueError('Unclassified purchased part: '+n)
    if s['material'] != 'SUS304':
        if n.startswith('Belt_Skirt_'):
            return dict(category='polymer', specification='스커트 고무 6×80×2120 mm',
                        length_m=2.120, note='2개 스트립; 식품 접촉 재질 확인')
        if n.startswith('Belt_'):
            return dict(category='polymer', specification='식품용 TPU 무단 벨트 670×6 mm',
                        note='모델 4조각을 무단 벨트 1개로 주문; 접합·장력 조정 길이 확인')
        raise ValueError('Unclassified nonmetal part: '+n)
    pending = {
        'Gate_Handwheel_Screw': ('게이트 리드스크루', '20×20×420 사각 외형만 있음; 나사·너트·실축 규격 확인'),
        'Gate_Handwheel': ('게이트 핸드휠', 'Ø140 링 외형; 주조·가공·구매 방식 미정'),
        'Outfeed_Coupling': ('배출 커플링', 'Ø50×47 외형; 보어·키홈·재질·구매 모델 확인'),
        'Exit_Lip': ('배출 경사 립', '모델 수직 두께 6 mm, 판 법선 두께 약 5.77 mm; 판재 규격 확정 필요'),
    }
    if n in pending:
        label, note = pending[n]
        return dict(category='pending', specification=label, note=note)
    if s.get('stock_section'):
        return dict(category='square_tube' if s.get('loops') else 'square_bar',
                    specification=s['stock_section']+' mm', length_m=d/1000,
                    note='모델 중심축 길이; 절단 톱날·단부 가공·정척 잔재 별도')
    if n.startswith('Gate_Slide_Guide_'):
        return dict(category='flat_bar', specification='15×30 mm', length_m=d/1000,
                    note='평철 또는 판재 절단 중 한 방식으로 견적; 중복 합산 금지')
    if n.startswith('Carry_Roller_Riser_'):
        return dict(category='square_bar', specification='50×50 solid mm', length_m=d/1000,
                    note='50×50×70 중실 받침 블록; 각봉 절단을 가정')
    if s['kind'] == 'circle' and not n.startswith('Drum_End_Disc_'):
        outer, inner = 2*s['radius'], 2*s.get('inner', 0)
        return dict(category='round_tube' if inner else 'round_bar',
                    specification=f'Ø{outer:g}×t{(outer-inner)/2:g} mm' if inner else f'Ø{outer:g} mm',
                    length_m=d/1000,
                    note='원형관 수급·진원도 확인; 후판 말이 제작 시 판재비와 중복 금지' if inner else
                         '완성 외형 기준; 선삭·나사·키홈·절단 및 가공 여유 별도')
    # Sheet thickness is not always the CAD extrusion depth.
    if s['kind'] == 'circle':
        thickness, w, h = d, 2*s['radius'], 2*s['radius']
    elif n.startswith('Hopper_Slope_'):
        thickness, w, h = c['side_sheet_mm'], d, math.dist(s['points'][0], s['points'][1])
    elif n.startswith('End_Stiffener_'):
        thickness = max(p[0] for p in s['points'])-min(p[0] for p in s['points'])
        w, h = d, max(p[1] for p in s['points'])-min(p[1] for p in s['points'])
    else:
        w, h = rectangle_blank(s['points'])
        if len(s['points']) == 4 and all(abs(s['axes'][i][i]-1) < 1e-9 for i in range(3)):
            thickness, w, h = sorted((w, h, d))  # axis-aligned box
        else:
            thickness = d
    w, h = sorted((w, h))
    return dict(category='plate', specification=f't{thickness:g} mm', thickness_mm=thickness,
                blank_width_mm=w, blank_length_mm=h, blank_area_m2=w*h/1e6,
                note='개별 부품 사각 소재 합계; 회전 배치 허용, 공용 네스팅·정판 장수·절곡 여유 미반영')


def takeoff(specs, c, bom):
    masses = {row['name']: row for row in bom}
    details = []
    for s in specs:
        q = classify(s, c)
        mass = masses[s['name']]['mass_kg']
        row = dict(name=s['name'], group=s['group'], material=s['material'], mass_kg=mass, **q)
        if q['category'] == 'plate':
            row['net_area_m2'] = masses[s['name']]['volume_m3']/(q['thickness_mm']/1000)
            row['blank_mass_kg'] = q['blank_area_m2']*q['thickness_mm']/1000*c['steel_density_kg_m3']
        details.append(row)
    grouped = {}
    for row in details:
        key = row['category'], row['specification']
        if key not in grouped:
            grouped[key] = dict(category=key[0], specification=key[1], model_count=0,
                                mass_kg=0., length_m=0., net_area_m2=0., blank_area_m2=0.,
                                blank_mass_kg=0., note=row['note'])
        q = grouped[key]
        q['model_count'] += 1
        for field in ('mass_kg', 'length_m', 'net_area_m2', 'blank_area_m2', 'blank_mass_kg'):
            q[field] += row.get(field, 0.)
    rows = sorted(grouped.values(), key=lambda q: (list(LABELS).index(q['category']),
                  float(q['specification'][1:-3]) if q['category'] == 'plate' else 0,
                  q['specification']))
    for q in rows:
        q['order_count'] = q['model_count']
        if q['specification'].startswith('식품용 TPU'):
            q['order_count'] = 1
            q['length_m'] = (2*2140+2*math.pi*103)/1000
            q['note'] += '; 이론 피치선 둘레 약 4.927 m'
        raw = q['category'] in ('square_tube', 'round_tube', 'round_bar', 'square_bar', 'flat_bar', 'plate')
        q['quote_unit'] = 'kg' if raw else '개/식'
        q['quote_quantity'] = (q['blank_mass_kg'] if q['category'] == 'plate' else q['mass_kg']) if raw else q['order_count']
    summary = []
    for category, label in LABELS.items():
        rr = [q for q in rows if q['category'] == category]
        summary.append(dict(category=category, label=label,
                            mass_kg=sum(q['mass_kg'] for q in rr),
                            length_m=sum(q['length_m'] for q in rr),
                            order_count=sum(q['order_count'] for q in rr)))
    return dict(revision='VBK-MATERIALS-1', density_kg_m3=c['steel_density_kg_m3'],
                rows=rows, summary=summary, details=details,
                accounted_mass_kg=sum(q['mass_kg'] for q in rows),
                plate_blank_mass_kg=sum(q['blank_mass_kg'] for q in rows),
                custom_casting_status='주문 제작 주물품의 재질·도면·중량은 명시되지 않음. 구매품 내부 주물 중량은 미확정.')


def write_csv(folder, material):
    for filename, rows in (('01_Material_Summary.csv', material['rows']),
                           ('01_Material_Detail.csv', material['details'])):
        fields = list(dict.fromkeys(key for row in rows for key in row))
        with (folder/filename).open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def render(r):
    from review_layout import table, fmt
    m = r['material_takeoff']
    rows = m['rows']
    e = html.escape
    content = '<h3>1번 원가 산정용 자재 물량</h3><p>현재 입력값의 실제 모델 형상에서 집계했습니다. SUS304 밀도 '+fmt(m['density_kg_m3'], 0)+' kg/m³ 기준입니다. 관 끝막음은 판재에, 축은 환봉에 한 번씩 포함합니다.</p>'
    content += table(['구분', '완성 형상·구매품 추정 중량 kg', '합계 길이 m', '절단품 / 구매 단위 수'], [
        (q['label'], fmt(q['mass_kg'], 3), fmt(q['length_m'], 3) if q['length_m'] else '—', q['order_count']) for q in m['summary']])
    content += '<p><b>집계 중량 '+fmt(m['accounted_mass_kg'], 3)+' kg</b> = 기존 BOM 중량. 구조 계산의 여유중량 '+fmt(r['mass_allowance_kg'], 3)+' kg를 더한 '+fmt(r['dead_mass_kg'], 3)+' kg는 설계하중용입니다. 그 여유를 자재 구매량에 다시 더하지 않았습니다.</p>'
    content += '<p><b>주물품:</b> '+e(m['custom_casting_status'])+' 베어링 하우징·감속기 케이스를 임의의 주물 kg로 환산하지 않고 완제품 견적에 포함하세요.</p>'
    content += '<h3>관재·봉재: 규격별 절단 총길이</h3>'+table(['구분', '단면 규격', '개수', '총 m', 'kg/m', '합계 kg'], [
        (LABELS[q['category']], q['specification'], q['model_count'], fmt(q['length_m'], 3),
         fmt(q['mass_kg']/q['length_m'], 3), fmt(q['mass_kg'], 3)) for q in rows if q['category'] in ('square_tube', 'round_tube', 'round_bar', 'square_bar', 'flat_bar')])
    content += '<p>길이는 모델의 완성 길이 합계입니다. 6 m 정척을 단순히 올림한 숫자는 절단 배치가 가능한 발주 수량을 보장하지 않습니다. 톱날 폭·가공 여유·끝단 손실을 넣어 절단 계획을 받아야 합니다. 각봉·평철은 현재 형상에 대한 원소재 가정이며, 다른 제작법을 택하면 해당 행을 대체합니다.</p>'
    content += '<h3>판재: 두께별 면적과 절단 전 소재</h3>'+table(['두께', '부품 수', '순면적 m²', '완성 kg', '사각 소재 m²', '사각 소재 kg'], [
        (q['specification'], q['model_count'], fmt(q['net_area_m2'], 3), fmt(q['mass_kg'], 3),
         fmt(q['blank_area_m2'], 3), fmt(q['blank_mass_kg'], 3)) for q in rows if q['category']=='plate'])
    content += '<p>사각 소재는 각 부품을 둘러싸는 절단 전 직사각형의 합계입니다. 구멍·도려낸 부분은 순중량에서 빠지지만 소재비에는 남습니다. 공용 네스팅으로 잔재를 재사용하면 줄고, 정판 가장자리·절단 간격·최소 주문량 때문에 늘 수 있으므로 실제 정판 장수와는 다릅니다. 19 mm 받침 등은 모델 치수이며 시장 재고 두께나 20 mm 소재 가공 여부를 확인하세요.</p>'
    content += '<h3>구매품·벨트·규격 확인품</h3>'+table(['구분', '품목', '구매 개/식', '참고 중량 kg', '확인할 내용'], [
        (LABELS[q['category']], q['specification'], q['order_count'], fmt(q['mass_kg'], 3), q['note']) for q in rows if q['quote_unit']!='kg'])
    content += '<p>베어링은 주 드럼 4개 + 지지 롤러 34개 + 배출 롤러 24개 = 62개입니다. 모터·감속기·제어반 질량은 구매품 추정값입니다. 벨트 4개 형상은 무단 벨트 1개이며 스커트는 2개입니다. 조립 롤러를 구매하면 관·축·베어링·스프로킷 중 견적에 포함된 행을 제외해 중복 합산을 피하세요.</p>'
    content += '<details><summary>개별 부품 절단 길이·판재 소재 치수 확인</summary>'+table(
        ['부품', '구분 / 규격', '길이 mm / 판 소재 W×L mm', '완성 kg'], [
            (q['name'], LABELS[q['category']]+' / '+q['specification'],
             fmt(q['length_m']*1000, 2) if 'length_m' in q else
             (fmt(q['blank_width_mm'], 2)+' × '+fmt(q['blank_length_mm'], 2) if 'blank_width_mm' in q else '별도 규격 확인'),
             fmt(q['mass_kg'], 3)) for q in m['details']])+'</details>'
    content += '<p><a href="01_Material_Summary.csv">엑셀용 규격별 물량 CSV</a> · <a href="01_Material_Detail.csv">엑셀용 부품별 상세 CSV</a></p>'
    content += calculator(rows)
    return content


def calculator(rows):
    e = html.escape
    out = '''<h3>견적 단가를 넣어 보는 계산표</h3>
<p>공급업체의 VAT 별도 단가를 입력하세요. 가격은 미입력 상태로 시작하며 저장 버튼으로 입력값이 담긴 HTML을 내려받을 수 있습니다. 판재는 사각 소재 kg, 관·봉재는 완성 형상의 kg가 기본 견적 수량입니다. 구매 수량 칸을 바꾸면 실제 정척·정판 견적량을 사용할 수 있습니다.</p>
<p>통합 구매품 견적에 포함된 자재 행은 체크를 해제하세요. 수량·단가에는 음수를 넣을 수 없습니다. 빈 단가는 0원 확정이 아닌 미견적입니다.</p>
<div class="scroll"><table id="material-estimate"><thead><tr><th>포함</th><th>품목</th><th>견적 수량</th><th>단위</th><th>단가 원</th><th>소계 원</th></tr></thead><tbody>'''
    for q in rows:
        name = LABELS[q['category']]+' / '+q['specification']
        out += '<tr><td><input type="checkbox" class="include" checked aria-label="'+e(name)+' 포함"></td><td>'+e(name)+'</td>'
        out += '<td><input type="number" min="0" step="any" class="quantity" value="'+f'{q["quote_quantity"]:.3f}'+'" aria-label="'+e(name)+' 수량"></td><td>'+e(q['quote_unit'])+'</td>'
        out += '<td><input type="number" min="0" step="any" class="price" placeholder="미견적" aria-label="'+e(name)+' 단가"></td><td class="subtotal">미견적</td></tr>'
    for label in ('절단·선삭·키홈·절곡 외주', '용접·조립·표면처리 공임', '전기 배선·시운전', '체결품·용접재·소모품', '포장·운송·설치', '간접비·이윤·기타'):
        out += '<tr><td><input type="checkbox" class="include" checked aria-label="'+label+' 포함"></td><td>'+label+'</td><td><input type="number" min="0" step="any" class="quantity" value="1" aria-label="'+label+' 수량"></td><td>식</td><td><input type="number" min="0" step="any" class="price" placeholder="미견적" aria-label="'+label+' 단가"></td><td class="subtotal">미견적</td></tr>'
    out += '''</tbody></table></div>
<p id="estimate-status" role="status" aria-live="polite">단가를 입력하면 입력 항목 소계를 계산합니다.</p>
<p>선택 항목 공급가 소계: <b id="estimate-net">0</b> 원 · VAT <input id="estimate-vat" type="number" min="0" step="any" value="10" aria-label="VAT 세율" style="width:60px"> % · VAT 포함 <b id="estimate-gross">0</b> 원</p>
<p>미견적 항목이 있거나 모델 밖의 체결품·배선·위생 마감 등이 확정되지 않으면 위 숫자를 기계 완성가격으로 사용하지 마세요. 자재 손실·공임을 추정 비율로 자동 추가하지 않았습니다.</p>
<button type="button" id="estimate-save">입력한 견적 HTML 저장</button> <button type="button" onclick="window.print()">인쇄 / PDF 저장</button>
<noscript>자동 견적 계산에는 JavaScript가 필요합니다. 위 물량과 CSV는 그대로 사용할 수 있습니다.</noscript>
<style>#material-estimate input[type=number]{width:110px;max-width:100%;box-sizing:border-box}#material-estimate .quantity{width:125px}#material-estimate input:invalid{outline:2px solid #b42318}button{padding:9px 14px;margin:6px 8px 6px 0;cursor:pointer}h3{margin-top:24px}</style>
<script>
(() => {
 const table = document.getElementById('material-estimate');
 const money = n => n.toLocaleString('ko-KR', {maximumFractionDigits:0});
 function update() {
   let total=0, missing=0, invalid=0, selected=0;
   for (const row of table.tBodies[0].rows) {
     const cell=row.querySelector('.subtotal');
     if (!row.querySelector('.include').checked) {cell.textContent='제외'; continue;}
     selected++;
     const qty=row.querySelector('.quantity'), price=row.querySelector('.price');
     if (qty.validity.badInput || price.validity.badInput || !qty.checkValidity() || !price.checkValidity()) {
       invalid++; cell.textContent='입력 확인'; continue;
     }
     if (qty.value==='' || price.value==='') {missing++;cell.textContent='미견적';continue;}
     const amount=Number(qty.value)*Number(price.value);
     if (!Number.isFinite(amount)) {invalid++;cell.textContent='입력 확인';continue;}
     total+=amount;cell.textContent=money(amount);
   }
   const vat=document.getElementById('estimate-vat');
   const validVat=vat.value!=='' && vat.checkValidity() && Number.isFinite(Number(vat.value));
   if (!validVat) invalid++;
   document.getElementById('estimate-status').textContent=`선택 ${selected}행 / 미견적 ${missing}행 / 입력 오류 ${invalid}행. `+(missing || invalid ? '입력 완료 항목만 합산한 부분 견적입니다.' : '선택 항목 합계입니다. 견적 범위와 제외 항목을 확인하세요.');
   document.getElementById('estimate-net').textContent=money(total);
   document.getElementById('estimate-gross').textContent=validVat ? money(total*(1+Number(vat.value)/100)) : '세율 확인';
 }
 document.querySelectorAll('#material-estimate input, #estimate-vat').forEach(el=>el.addEventListener('input',update));
 document.getElementById('estimate-save').addEventListener('click',()=>{
   const clone=document.documentElement.cloneNode(true);
   const source=document.querySelectorAll('input');
   clone.querySelectorAll('input').forEach((el,i)=>{
     el.setAttribute('value',source[i].value);
     if (source[i].type==='checkbox') el.toggleAttribute('checked',source[i].checked);
   });
   const url=URL.createObjectURL(new Blob(['<!doctype html>\\n'+clone.outerHTML],{type:'text/html;charset=utf-8'}));
   const link=document.createElement('a');link.href=url;link.download='01_VBK_견적_입력본.html';link.click();
   setTimeout(()=>URL.revokeObjectURL(url),1000);
 });
 update();
})();
</script>'''
    return out
