# 감자칩 라인 통합 소스 — R13 / 5~11번 용접 구조·디자인 리뷰

현재 구성:

| 번호 | 적용 상태 |
|---|---|
| 1 | SUS304 용접 호퍼·컨베이어 + 관 사이 보강판·경사/수직 맞댐 수정 + 계산서 R4.1 |
| 2 | 용접 프레임·십자 지지대 + Rib 나선 + 계산서 |
| 3 | 용접 프레임·투입 캐비닛 외장 제거·입출구 지지 보강 + 계산서 |
| 4 | 기존 탈피 기구 유지·프레임/입출구 지지 보강 + 계산서 |
| 5 | CC-DL 원심 슬라이서 R16: 고정 1.5 mm 칼날·800 mm 공급기·SUS304 용접 사각관, 계산서 |
| 6 | Blancher: 프레임과 판재 간섭 수정, 수조·구동부 지지, 물/가열 포함 계산서 |
| 7 | Vibratory Dewaterer: 용접 프레임·진동부 지지, 스프링/진동기 계산서 |
| 8 | Air Dryer: Deck~Lift 연속 측면 가이드, 외측 베어링 지지, 용접 구조, 계산서 |
| 9 | Fryer: 모터 양측 분리·후드 여유 확보, 용접 지지, 기름/가열/리프트 계산서 |
| 10 | Vibratory Deoiler: 용접 프레임·진동부 지지, 튀긴 칩 밀도 기준 계산서 |
| 11 | Seasoning Drum: 지면부터 연결한 지지대·배출구 하부 지지, 용접 구조, 계산서 |

이 폴더의 Python 파일을 함께 보관하세요. `build_line.py`만 교체하면 의존 모듈을 찾지 못합니다.
세부 실행은 `README_STATION1_KO.md`, `README_STATION2_KO.md`, `README_PEELERS_KO.md`,
`README_STATION5_KO.md`, `README_FINISHING_KO.md`에 있습니다. 1~4번 설계 모듈은 유지했습니다.

```powershell
# 계산서만 생성 — CATIA 불필요
py build_line.py --stages 5 6 7 8 9 10 11 --report-only --finish-config finishing_config.json
# 5번부터 순서대로 새 모델 생성·저장
py build_line.py --stages 5 6 7 8 9 10 11 --rebuild --finish-config finishing_config.json
# 중단된 다음 기기부터 재개하는 예
py build_line.py --stages 9 10 11 --finish-config finishing_config.json
# 전체 라인 조립
py build_line.py --assemble --finish-config finishing_config.json --zip
```

인자 없는 실행은 기존대로 1번 보고서만 생성합니다. 전체 모델은 `--all` 또는 `--assemble`을 명시하세요.
`--report-only`는 1~11번에 사용할 수 있고 CATIA/pywin32가 필요 없습니다.
5~11번 리뷰 목록은 `05_11_Design_Review_Index.html`입니다.
모델은 각 기기를 저장한 뒤 다음 기기로 넘어가며, 완성 모델은 재사용하고 `--rebuild`는 새 폴더에 생성합니다.
모델 생성에는 Windows, CATIA V5, pywin32가 필요합니다. 이번 작업에서는 CATIA를 실행하지 않았습니다.

1~4번 사용자 설정을 적용하려면 해당 기기를 포함하는 명령에 `--vbk-config station1_config.json`,
`--so-config station2_config.json`, `--crp-config station3_config.json`, `--ms-config station4_config.json`을 추가합니다.
`README_MERGED_R11_KO.md`는 과거 통합 기록이며 현재 기준은 이 문서와 R13 리뷰입니다.

생성물 정리 옵션을 추가했습니다. `py build_line.py --clean --dry-run`은 미리보기,
`py build_line.py --clean`은 모델·리포트·모델 ZIP 실제 삭제입니다.
`--clean models`와 `--clean reports`로 범위를 나눌 수 있습니다. `clean_outputs.py`를 함께 보관하세요.
소스·설정·백업은 보존합니다. 세부 대상과 명령은 `README_CLEANUP_KO.md`에 있습니다.

5번의 18번째 `Lower_Discharge_Cone`에서 발생한 Shaft Update 오류에 대해
스케치 회전축 등록(`CenterLine`)과 축 구속을 수정했습니다. 재실행은 `README_SHAFT_FIX_KO.md`를 참조하세요.

본 프로젝트의 코드는 생성형 AI에 의해 생성되었습니다.