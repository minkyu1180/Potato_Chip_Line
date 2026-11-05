# 1~11번 통합 R11 / 2번 나선 오류 수정

2026-11-01. `build_line.py`, `station1_design.py`, `station2_design.py`, `station5_bsm150.py`를 같은 폴더에 두세요.
이 패키지는 파이썬 소스와 1·2번 계산서입니다. 새 CATIA 모델을 미리 실행해 만든 패키지는 아닙니다.

## 반영 범위

- 1번: 기존 SUS304 용접 사각관, 형상 치수, 계산·보고서, 기능별 Product 그룹 유지.
- 2번: 기존 용접 프레임, 십자 지지대, 지지 배출부, 형상 치수·계산 유지.
- 2번 오류: `AddSectionToLoft`를 호출하던 다중단면 Loft를 제거하고 나선 경로 + 단일 구속 스케치의 native Rib으로 변경. 기존 최소 법선 두께 보정 유지.
- 3·4·6~11번: 사용자가 지정한 `C:/Users/Jaehyun/Downloads/build/build_line.py`의 R10 초안, 공통 형상 함수, 옵션 및 Product 분류를 통합.
- 5번: 이후 제공된 `C:/Users/Jaehyun/Downloads/5.py`의 BSM-150으로 교체. 형상 코드는 `station5_bsm150.py`에 원본 그대로 보관.
- 3·4·6~11번의 프로파일은 제공된 초안의 중실 등가 단면 표현 그대로입니다. 1·2번의 구조 계산을 나머지 장비에 확대 적용하지 않았습니다.
- 1·2번 Product 트리는 기존 기능별 큰 단위를 유지합니다. 3·4·6~11번은 초안의 Frame / Internal Geometry / External Controls 분류, 5번은 제공된 10개 CATPart 구성을 유지합니다.
- 전체 조립은 현재 2번의 직선 투입/토출 방향에 맞춰 +X 방향으로 연결합니다. 각 장비의 실제 포트 높이에 맞는 연결 컨베이어를 생성합니다.

원본 다운로드 파일은 변경하지 않았습니다. 작업 폴더의 수정 전 `build_line.py`는
`build_line_before_merge_03_11_and_rib.py.bak`로 보관했습니다.

## 2번 재실행

```powershell
py build_line.py --stage 2 --so-config station2_config.json --rebuild
```

실패 당시의 CATPart·CATProduct는 보존합니다. 같은 모델 폴더가 있으면 `_r11_01` 등 새 번호 폴더로 저장합니다.
완성 모델을 반드시 새로 만들 때는 `--rebuild`를 붙이세요.
이전 계산서의 모델 폴더가 남아 있는 것만으로 생성 완료된 것은 아닙니다.

## 3~11번 생성 및 조립

```powershell
py build_line.py --stages 3 4 5 6 7 8 9 10 11 --zip
py build_line.py --all --zip
py build_line.py --assemble --zip
```

장비별 저장이 끝난 뒤 다음 장비로 넘어갑니다. `--zip`은 각 모델의 native 파일을 묶습니다.
`--assemble --zip`은 전체 CATProduct와 참조하는 장비·연결부 파일을 함께 묶습니다.
1·2번은 이전 기능대로 별도 모델 ZIP도 자동 생성합니다.

```powershell
py build_line.py --stage 5 --slice-thickness 3
py build_line.py --stage 9 --fryer-model PC4 --hood-lift 500
py build_line.py --stage 11 --seasoning-angle 40
py build_line.py --stages 1 2 --report-only
```

인자 없는 실행은 기존대로 **1번 보고서만 생성**합니다. 전체 모델을 만들려면 `--all` 또는 `--assemble`을 명시하세요.
`--report-only`는 CATIA/pywin32 없이 사용할 수 있습니다. 모델 생성에는 Windows, CATIA V5, pywin32가 필요합니다.

## 확인 범위

3·4·6~11번의 형상 데이터와 부품 분류가 가져온 파일과 같은지 비교했습니다. 5번은 제공 파일과 소스가 바이트 단위로 동일한지 확인했습니다.
1·2번의 계산/보고서 진입점, 나선 Rib API 호출 구성, 조립 포트 배치를 Python에서 점검했습니다.
CATIA를 실행하거나 실제 COM 형상 업데이트 성공을 확인한 것은 아닙니다.

Rib/Helix API 구성 참고: Dassault Systèmes CAA V5 문서의
[ShapeFactory](https://catiadesign.org/_doc/V5Automation/generated/interfaces/PartInterfaces/interface_ShapeFactory_20269.htm),
[Sweep](https://catiadesign.org/_doc/V5Automation/generated/interfaces/PartInterfaces/interface_Sweep_14280.htm),
[Helix 예제](https://catiadesign.org/_doc/V5Automation/online/CAAScdGsiUseCases/CAAGsiCreateStairSource.htm).
