# 1번 감자 투입 호퍼 — SUS304 용접식 R4.1

`build_line.py`와 `station1_design.py`를 같은 폴더에 두세요.
이 패키지는 1번의 코드와 계산서를 수정한 것이며 새 CATProduct를 실행해 검증한 파일은 아닙니다.
통합 R12에서 1번 보강재를 R4.1로 수정했습니다. 2번 용접 설계, 3·4번 R12 설계 리뷰,
6~11번 사용자 제공 R10 초안, 5번 BSM-150 초안을 유지합니다.

## R4.1 보강재 수정

- `Slope Stiffener`와 `Collar Stiffener`를 기둥 사이에 배치했습니다. 기본 사각관안에서 보강판 중심 X는
  144, 448, 752, 1056, 1144, 1448, 1752, 2056 mm입니다. 판 두께 8 mm 전체가 기둥 외면 사이에 들어갑니다.
- 두 보강판의 접합부는 같은 사선 끝면으로 맞댑니다. 관통하거나 중첩시킨 연결이 아닙니다.
- 보강판 상단은 상부 사각관 아랫면인 Z=2130 mm에서 끝납니다.
- 후면 `End Stiffener`는 대각 가새 외면에서 분할하고 사선 절단해 맞댑니다.
- 전면 중앙 보강판은 새 `Front Gate Header` 위에서 시작합니다. 기본안 헤더는 80×80×5 mm 사각관,
  길이 1492 mm이며 외측 보강판 사이에 맞댑니다. 게이트 최대 상승 위치와 헤더 사이 명목 여유는 10 mm입니다.
- 경사판 계산 경간은 실제 최대 간격 304 mm로 갱신했습니다. 게이트 위 판의 자유단 구간과 헤더는 따로 계산합니다.
  수정 형상의 자중, 반력, 응력, BOM은 Python 실행 때 함께 다시 계산합니다.

이 치수는 용접 전 명목 맞춤 기준입니다. 관 모서리 반경, 용접 루트 간격, 절단 공차와 접합부 국부 내력은
디자인 리뷰의 상세 설계 항목으로 남겨 두었습니다. CATIA 실행·실제 간섭 검증은 수행하지 않았습니다.

## 바로 보고서 보기

`01_VBK_Design_Review/01_VBK_Design_Review.html`을 브라우저로 열면 됩니다.
설명, 계산식, 출처, 부품별 질량 명세까지 들어 있는 단일 HTML입니다.
파일 안의 **인쇄 / PDF 저장** 버튼으로 PDF로 보관할 수 있습니다.

## 실행

Python 3.10 이상. **보고서만 만들 때는 pywin32와 CATIA가 필요 없습니다.**

```powershell
py build_line.py --stage 1 --report-only
```

아무 인자 없이 `py build_line.py`를 실행해도 1번 보고서만 만듭니다.

모델까지 만들려면:

```powershell
py build_line.py --stage 1 --vbk-config station1_config.json --rebuild
```

먼저 `01_VBK_Design_Review` 폴더에 보고서 경로를 출력한 뒤 CATIA에 연결합니다.
완료 시 `01_VBK_Welded_R4_1_TUBE` 폴더에 CATProduct, Parts, 기능별 Subassemblies와 계산서 사본을 저장합니다.
기존 `01_VBK_2020` 모델은 덮어쓰지 않습니다. 같은 이름의 폴더가 있으면 새 번호 폴더를 만들며, 완성된 동일 모델은 재사용합니다. `--rebuild`로 새로 생성할 수 있습니다.
다시 생성하려면 새 폴더를 지정하세요.

```powershell
py build_line.py --stage 1 --vbk-config station1_config.json --output-dir D:\CATIA\VBK_R4_1_Run2
```

모델 생성에는 Windows, CATIA V5, pywin32가 필요합니다.
보고서는 CATIA 연결에 실패해도 먼저 저장됩니다. 모델 폴더의 계산서는 모델 생성 중 실패할 때도 남을 수 있으므로,
CATProduct 저장 완료 메시지와 BUILD_STATUS.json을 함께 확인하세요.

## 입력값 변경

`station1_config.json`은 변경할 값만 적은 JSON입니다.
주요 항목:

| 입력 | 단위/의미 |
|---|---|
| target_kg_h | 원료 감자의 목표 kg/h. 완제품 감자칩 처리량 아님 |
| working_mass_limit_kg | 정상 운전 적재 제한 kg |
| gate_opening_mm | 게이트 개도, 80–300 mm |
| packing_fraction | 감자 고체 점유율, 0.65 기본 |
| potato_density_kg_m3 | 감자 실질 밀도, 1100 기본 |
| headspace_mm | 상부 여유높이, 150 기본 |
| running_hopper_coefficient | 정상 인출저항 가정 |
| starting_hopper_coefficient | 기동 인출저항 가정 |
| assumed_all_in_energy_krw_kwh | 세금·조정액을 포함한다고 가정한 총 변동단가 |
| incremental_demand_charge_krw_month | 계약 증설 등 추가 기본/수요요금만 별도 입력 |
| hours_per_day, days_per_month | 근무시간/일수 |
| running_fraction | 근무시간 중 가동 비율, 0–1 |
| frame_type | tube 또는 solid. 기본 tube; 두 안의 비교는 항상 보고서에 포함 |

전체 입력과 단위는 보고서 11번 및 `station1_design.py` 상단 `DEFAULTS`에 있습니다.
관 치수는 같은 파일의 `sections()`에서 결정합니다. 현재 tube안: 기둥 80×80×5, 횡보 160×160×8,
세로 레일 100×100×6, 가새 50×50×4 mm. 형상과 자중 계산은 이 공통 단면을 사용합니다.
단면을 변경할 때는 모델의 접합 위치, 관 끝 캡, 장착 높이도 함께 검토하세요.

입력 변경 후 위 명령을 다시 실행하면 HTML과 JSON 계산 결과가 갱신됩니다.
기존 계산서를 보존하려면 `--output-dir`를 다르게 지정하세요.

## 모델 구성

- Welded Support Frame
- Hopper and Reinforcement
- Metering Gate
- Live Bottom Conveyor
- Outfeed Roller Conveyor
- Drive Systems
- Electrical Controls

사각관은 중공 단면 Sketch/Pad와 밀폐 캡으로 생성합니다. 기준평면과 소비된 스케치는 숨깁니다.
기존의 좌표·반지름 구속 방식을 유지합니다. 실제 CATIA에서의 구속 상태·간섭·형상 검토는 실행 후 확인하세요.
용접 비드, 키홈, 나사산, 실제 체인 링크, 벨트 접합부 및 구매품 내부는 상세 제작 형상이 아닙니다.
구매품은 봉투 형상으로 표현하며 질량은 별도 추정값으로 계산합니다.

CATPart의 `Engineering_Material`은 재질 사양을 표시하는 문자열입니다.
사용자 설치 환경마다 다른 CATIA 재질 카탈로그를 자동 적용했다고 주장하지 않습니다.
CATIA 관성 측정에 쓰려면 실제 Material을 지정하세요. 보고서는 자체 체적×SUS304 밀도와 구매품 질량으로 계산합니다.

## 계산서 해석

사용자 확인 재질은 **SUS304**입니다. 304L로 임의 변경하지 않았습니다.
기본 1,000 kg/h는 가정한 목표이며 전체 라인 CAPA가 확정되면 변경하세요.
계산서의 '조건 충족'은 표시한 수식과 가정의 범위입니다. 피로수명·공진·용접 국부파괴·바닥/앵커 내력까지
제작 승인된 뜻은 아닙니다. 전체 자중이 큰 보수적 안이므로 경량화 검토 항목도 10번에 기재했습니다.
전기요금 160원/kWh는 공식 한전 단가가 아닙니다. 사업장 고지서 기준으로 교체할 수 있습니다.

상세 수치가 필요한 경우 `01_VBK_Calculations.json`에 계산 중간값·입력 해시·BOM도 저장됩니다.

## 원가 산정용 자재 물량

1번 리뷰의 5절에는 `station1_materials.py`가 집계한 관재·환봉·각봉·평철·판재·구매품 물량이 들어갑니다.
이 모듈도 다른 Python 파일과 함께 보관하세요. `--report-only` 실행 시 HTML과 함께
`01_Material_Summary.csv`(규격별), `01_Material_Detail.csv`(부품별)를 UTF-8 BOM 형식으로 저장합니다.

관·봉재는 완성 길이와 중량, 판재는 순면적·순중량과 개별 사각 소재 합계를 구분합니다.
사각 소재는 정판 네스팅이나 실제 발주 장수를 확정한 값이 아닙니다. 절단·가공 여유와 공급 단위를 별도 확인하세요.
현재 모델에 주문 제작 주물품의 재질·도면·중량은 명시되지 않았습니다. 구매품 내부 주물을 임의 환산하지 않습니다.

HTML 견적표에서 수량·단가를 입력하거나 조립 구매품에 포함된 행을 제외할 수 있습니다.
공임·체결품·운송·간접비 등은 별도 행이며 빈 단가는 미견적으로 남습니다. 단가는 자동 제공하지 않습니다.
입력값을 보관하려면 **입력한 견적 HTML 저장**을 누르세요. 다운로드한 HTML의 CSV·JSON 링크를 사용하려면
원본 리뷰와 같은 폴더에 두세요. 페이지를 새로 열거나 보고서를 재생성하면 저장하지 않은 입력은 보존되지 않습니다.
