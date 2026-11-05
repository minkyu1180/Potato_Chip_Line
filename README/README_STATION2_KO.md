# 2번 습식 나선 제석기 — SUS304 용접 / 십자 지지 R5

원본 `build_line.py`의 2번 생성 함수를 수정했습니다. 통합 R11에는 1번 R4와 사용자 제공 3~11번 초안도 포함합니다.
`build_line.py`, `station1_design.py`, `station2_design.py` 세 파일을 같은 폴더에 두세요.
학원에서 따로 수정한 CATProduct는 덮어쓰지 않습니다. 새 모델 이름은 `02_SO_Welded_CrossSupport_R5`입니다.

## 요청에 반영한 내용

- 주 구조: SUS304 밀폐 용접 사각관, 가새·관 끝 캡.
- P006: 사용자 설명에 따라 **위쪽 나선/모터 지지대**를 네 방향 십자 보로 교체.
- 상부: 중앙 받침판, M16 4개를 90° 간격으로 배치, 별도 스러스트/방사 베어링.
- 하부: 물 윤활 폴리머 방사 가이드. 스크루 축하중은 위쪽으로 전달.
- 토출부: 슈트 세로 보, 후방 받침, 전방 받침·다리 두 개. 케이싱 박판에만 매달지 않음.
- 투입: 1번의 배출 높이에 맞춘 1,000 mm 창과 내부 유도 슈트. 창/청소구는 실제로 뚫음.
- 코드/계산 공유: 수조·관·판·나선 치수, 물 배제 체적, 부품 자중, 응력, 구동·전력 계산.
- 스케치 좌표 구속과 평면 숨김을 유지. 나선 날개는 최소 법선 두께를 보정한 단일 단면 + 나선 경로의 native Rib으로 생성.
- R5.1: `AddSectionToLoft` 오류가 발생한 다중단면 Loft 호출을 제거. 기존·실패 모델 폴더가 있으면 새 번호 폴더로 생성.

`Profile Cross`/원본 `Frame_Cross`는 가로 보강재로서 벌어짐·비틀림을 줄입니다.
감자를 나선으로 끌어들이는 부품은 아닙니다. 실제 공급에는 유입 슈트, 케이싱, 수위, 회전방향/속도가 관여합니다.

## 실행

Python 3.10 이상. 보고서만 생성할 때는 CATIA와 pywin32가 필요 없습니다.

```powershell
py build_line.py --stage 2 --report-only
```

또는 `station2_design.py`만 직접 실행해도 2번 보고서를 만듭니다.

CATIA 모델과 보고서 생성:

```powershell
py build_line.py --stage 2 --so-config station2_config.json
```

모델 생성에는 Windows, CATIA V5, pywin32가 필요합니다. CATIA 실행/형상 검증은 이번 작업에서 수행하지 않았습니다.
같은 이름의 폴더가 이미 있으면 새 번호 폴더에 생성합니다. 동일한 최신 모델이 완성돼 있으면 재사용합니다.
오류 뒤 확실하게 새 모델을 만들려면 `--rebuild`를 붙이세요. 기존 모델과 부분 작업은 보존합니다.

```powershell
py build_line.py --stage 2 --so-config station2_config.json --rebuild
```

보고서는 먼저 `02_SO_Design_Review` 폴더에 저장됩니다. CATIA 연결에 실패해도 먼저 생성한 보고서는 남습니다.
모델이 완성되면 모델 폴더에도 보고서 사본과 계산 JSON을 넣고 ZIP으로 묶습니다.
실패 도중 남은 모델 폴더의 보고서만 보고 CATProduct 생성이 완료되었다고 판단하지 마세요.

1·2번 계산서를 함께 만들려면:

```powershell
py build_line.py --stages 1 2 --report-only
```

인자 없는 `build_line.py` 실행은 기존 동작을 유지해 **1번 보고서**를 생성합니다.

## 보고서

`02_SO_Design_Review/02_SO_Design_Review.html`은 사진/외부 글꼴/네트워크 의존성이 없는 단일 파일입니다.
브라우저에서 열거나 인쇄/PDF 저장 버튼을 사용할 수 있습니다. 상세 입력, BOM, 계산식은 펼침 항목에 포함됩니다.
JSON 계산 원본은 같은 폴더의 `02_SO_Calculations.json`입니다.

보고서에는 용적, 정상 재고/물 무게, 이상 만재, 각 하중 경로, 응력/처짐/좌굴, 볼트 축력,
용접군 선별, 스크루/모터 RPM, 기동/정상 토크, 전력·요금, 진동/피로 미확정 사항, 출처를 담았습니다.

## 변경 가능한 주요 입력

`station2_config.json`을 편집하고 다시 실행합니다.

| 키 | 단위/의미 |
|---|---|
| working_potato_kg | 수조 안 정상 감자 재고, 기본 200 kg |
| water_level_z_mm | 바닥 기준 수면 높이, 기본 900 mm |
| target_kg_h | 원료 목표 유량, 기본 1000 kg/h |
| screw_rpm | 기준 스크루 회전수, 기본 30 rpm |
| flight_loading_fraction | 환형 공간 점유율, 실측 전 가정 |
| axial_transport_efficiency | 피치 대비 실제 축방향 이송 비, 실측 전 가정 |
| jam_loading_fraction | 기동 시 정체 감자 충전율 |
| vertical_dynamic_factor | 수직 중량에 곱하는 동하중 계수 |
| lateral_accel_g | 수평 등가 진동 가속도 / g |
| motor_kw, gear_ratio, torque_limiter_nm | 주 구동 구매 요구사양 |
| energy_rate_krw_kwh | 세금·조정액 포함 가정 총 변동단가. 공식 한전 요금표 아님 |
| extra_demand_charge_krw_month | 증설 등 추가 기본/수요요금 |

전체 입력은 `station2_design.py`의 `DEFAULTS`와 보고서에 있습니다. 형상 치수는 같은 파일의 `DIM`에서 공통 사용합니다.
일부 장착 좌표/패드/포켓은 기준안에 맞춘 상세 위치이므로 `DIM`만 대폭 변경하면 모든 접속이 자동으로 유지되지는 않습니다.
구매품 외형/질량은 봉투 형상과 추정값입니다. 실제 선택 모델로 갱신하세요.

## 계산의 의미

목표 유량은 **원료 감자 16.7 kg/min**입니다. 계산상의 전달능력은 실제 습식 성능 검증값이 아닙니다.
건식 수직 스크루의 고속 권장 RPM을 감자 제석기에 그대로 적용하지 않았습니다.
기준안의 30 rpm과 계수는 시험·시운전으로 확인해야 합니다. 저속에서는 투입도 함께 낮춰야 합니다.

물과 감자를 동시에 고려할 때 감자가 밀어낸 물의 체적을 차감했습니다. 정상 재고 200 kg와
기하학적 최대 적재 가능량을 구분했으며, 구조 검토에는 별도의 비정상 만재 경우도 포함합니다.
수직 증폭 2.0과 수평 0.30g는 진동 실측값이 아닙니다. 용접 피로수명, 전체 구조의 모드,
콘크리트/앵커 내력, 실제 이송 성능까지 제작 승인된 뜻은 아닙니다.

재질 사양은 CATPart의 `Engineering_Material` 등에 표시합니다. CATIA의 물성 카탈로그를 자동 적용했다는 뜻이 아닙니다.
CATIA 질량/관성 측정을 하려면 실제 재질을 별도 지정하세요. 보고서는 자체 기하/구매품 질량 계산을 사용합니다.

## Product 그룹

- Welded Base Frame
- Wet Separation Tank
- Infeed
- Screw Rotor
- Screw Casing
- Screw Support and Bearings
- Drive System
- Supported Outfeed
- Electrical Controls

3·4번은 R12 설계 리뷰, 6~11번은 사용자가 제공한 `Downloads/build/build_line.py`의 R10 초안, 5번은 이후 제공한 `Downloads/5.py`의 BSM-150 초안으로 교체했습니다.
해당 장비의 프로파일·기구·구매품 표현은 초안 그대로이며, 1·2번의 용접/강도 계산을 3~11번에 확장한 것은 아닙니다.
