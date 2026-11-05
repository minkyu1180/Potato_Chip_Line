# 3·4번 용접 지지 보강 / 디자인 리뷰 R12

1·2번과 5번 BSM-150, 6~11번 형상은 유지했습니다. CATIA는 실행하지 않았습니다.

## 반영 내용

- 3번: Feed Cabinet 외장·옆판·손잡이 제거. 사용자가 확인한 대로 내부 유도판과 본체 서비스 커버 유지.
- 3번: 주 프레임을 밀폐 SUS304 사각관 용접 구조로 교체. 중간 지지 기둥, 가새, 발판, 거싯 추가.
- 3번: 중실로 표현됐던 롤러 중심부를 중공 코어와 끝판으로 변경. 구동축 하중을 고려해 롤러 축은 Ø40 mm 기준.
- 4번: 기존 드럼·칼날·현수 벨트·본체 커버 형상 유지. 자중을 받는 주 지지 프레임과 중간 기둥 보강.
- 공통: 투입·배출 각각 t6 바닥/측판, 아래쪽 보, 가로 받침 2개, 다리 4개, 거싯·가새·본체 연결 타이.
- 공통: 모델 치수·질량을 바탕으로 용량, 물질수지, 응력/처짐/좌굴, 기동 토크, 모터, 380 V 3상 전력·요금을 계산.

용접 구조와 정비 부품은 구분합니다. 베어링·모터·커버는 분해 가능한 상태를 유지합니다.
용접 비드와 구매품 내부는 단순화하며, 상세 가공도까지 완료된 뜻은 아닙니다.

## 실행

다음 6개 파이썬 파일을 같은 폴더에 두세요.

- `build_line.py`
- `station1_design.py`
- `station2_design.py`
- `peeler_design.py`
- `peeler_report.py`
- `station5_bsm150.py`

보고서만 생성:

```powershell
py build_line.py --stages 3 4 --report-only
```

모델과 보고서를 순서대로 생성:

```powershell
py build_line.py --stages 3 4 --crp-config station3_config.json --ms-config station4_config.json --rebuild
```

3번을 저장하고 ZIP을 만든 뒤 4번을 생성합니다. 실패 이전 장비의 저장 파일은 남습니다.
`--rebuild`는 기존 모델을 지우지 않고 새 번호 폴더에 저장합니다.

보고서 경로:

- `03_CRP_Design_Review/03_CRP_Design_Review.html`
- `04_MS_Design_Review/04_MS_Design_Review.html`

각 폴더에 계산 원본 JSON도 저장합니다. 보고서는 CATIA 연결 전에 먼저 생성되고 모델 폴더에도 사본을 넣습니다.
보고서 존재만으로 CATProduct 생성이 완료됐다고 판단하지 마세요.

직접 보고서 실행도 가능합니다.

```powershell
py peeler_design.py --stage 3 --config station3_config.json
py peeler_design.py --stage 4 --config station4_config.json
```

## 입력 및 판정

`station3_config.json`, `station4_config.json`에서 유량·탈피 손실·RPM·모터·하중 계수·전력 단가를 수정할 수 있습니다.
나머지 입력은 `peeler_design.py`의 `COMMON`, `STAGE_DEFAULTS`, 구조 치수는 `DIM`에 있습니다.
큰 치수 변경은 기존 본체와 연결 위치의 재검토가 필요합니다.

기본 라인 물질수지는 3번 1000→900 kg/h, 4번 900→864 kg/h입니다. 손실율 10%, 4%는 가정입니다.
3번을 바꾸면 4번의 입력 유량도 직접 맞춰 주세요. 정상 내부 재고와 비정상 정체 재고는 서로 다른 계산입니다.

이번 안은 기존 두꺼운 본체·회전체와 새 프레임을 포함해 무겁습니다. 보고서의 자중은 실제 Sormac 구매 기계 중량이 아닙니다.
보고서의 조건 충족은 정적 등가 선별입니다. 실제 탈피 비에너지, 이송효율, 진동, 구매 벨트/베어링 정격, 용접 피로,
베어링 좌대/스파이더 국부 굽힘, 앵커·슬래브, 실제 모터 외형과 정격의 일치는 아직 확인되지 않았습니다.
특히 3번 타이밍 벨트 외형은 기존 초안이므로 계산된 전달력에 맞는 구매품과 풀리 폭을 별도로 확정해야 합니다.

모터·제어함은 구매품 추정 질량, 판·관·축은 기하 체적×밀도로 계산합니다.
CATIA 재질 카탈로그 자동 적용이나 실제 CATIA 질량 측정 결과를 주장하지 않습니다.

수정 전 소스는 `build_line_before_peelers_engineering.py.bak`로 보관했습니다.
