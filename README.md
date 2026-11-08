# 감자칩 라인 통합 소스 — R23 / 기계 생성 메모리 부담·중단 복구 개선

현재 구성:

| 번호 | 적용 상태 |
|---|---|
| 1 | SUS304 용접 호퍼·컨베이어 + 관 사이 보강판·경사/수직 맞댐 수정 + 계산서 R4.1 |
| 2 | 용접 프레임·십자 지지대 + Rib 나선 + 계산서 |
| 3 | 용접 프레임·투입 캐비닛 외장 제거·입출구 지지 보강 + 계산서 |
| 4 | 기존 탈피 기구 유지·프레임/입출구 지지 보강 + 계산서 |
| 5 | CC-DL 원심 슬라이서 R17: 외부 감속기 간섭 수정·밀폐 축 보호관·용접 사각관·계산서 |
| 6 | Blancher: 프레임과 판재 간섭 수정, 수조·구동부 지지, 물/가열 포함 계산서 |
| 7 | Vibratory Dewaterer: 용접 프레임·진동부 지지, 스프링/진동기 계산서 |
| 8 | Air Dryer: Deck~Lift 연속 측면 가이드, 외측 베어링 지지, 용접 구조, 계산서 |
| 9 | Fryer: 모터 양측 분리·후드 여유 확보, 용접 지지, 기름/가열/리프트 계산서 |
| 10 | Vibratory Deoiler: 용접 프레임·진동부 지지, 튀긴 칩 밀도 기준 계산서 |
| 11 | Seasoning Drum: 지면부터 연결한 지지대·배출구 하부 지지, 용접 구조, 계산서 |
| 12 | 독립 계량 10채널·VFFS 10대, 원본 형상 유지·개별 리뷰·부품과 하위 Product를 저장 직후 닫는 방식 |

이 폴더의 Python 파일을 함께 보관하세요. `build_line.py`만 교체하면 의존 모듈을 찾지 못합니다.
현재 실행 방법과 파일 구조는 [사용 설명서](README/README_RUN_01_12.md)에 있습니다.
1~4번·6~11번은 모든 고유 부품을 저장하고 닫은 뒤 기능별 Product를 만들고,
최종 기계 Product는 마지막에 조립합니다. `--all`·`--stages`도 이전 기계 창을 닫고 다음으로 진행합니다.
8번 RPC 오류 후 재개: CATIA를 재시작하고 `py build_line.py --stage 8`을 실행하세요.
`--rebuild`를 빼야 저장된 형상과 입력이 일치하는 부품을 복사·재사용합니다.
`engineering_assembly.py`를 포함해 같은 폴더의 모든 Python 모듈이 필요합니다.
전체 조립의 `AddExternalComponent` 실패를 피하도록 파일 경로로 삽입하는 방식으로 변경했습니다.
구버전 연결부는 기존 CATPart를 복사해 고유 부품 번호와 별도 저장된 하위 Product로 복구합니다.
복구·재조립 명령은 `py build_line.py --assemble-existing`입니다. 원본 기계 파일은 보존합니다.

```powershell
# 기본: 1~12번 생성/재사용 + 리뷰 + 전체 CATProduct
py build_line.py
# 저장된 기계만 사용해서 전체 조립
py build_line.py --assemble-existing
# 기존 기계로 4번 제외 조립: 1→2→3→5→6→…→12
py build_line.py --assemble-existing --exclude-stage 4
# 필요한 기계 생성/재사용부터 4번 제외 조립까지
py build_line.py --exclude-stage 4
# 전체 리뷰만 생성 — CATIA 불필요
py build_line.py --report-only
# 12번만 생성
py build_line.py --stage 12
# 전체 조립과 참조 파일을 ZIP으로 저장
py build_line.py --assemble --zip
```

인자 없는 실행은 전체 모델 생성과 조립을 시작합니다. 리뷰만 필요하면 `--report-only`를 명시하세요.
`--report-only`는 1~12번에 사용할 수 있고 CATIA/pywin32가 필요 없습니다.
전체 리뷰 목록은 `Overall_Review/01_12_Design_Review_Index.html`입니다.
모델은 각 기기를 저장한 뒤 다음 기기로 넘어가며, 완성 모델은 재사용하고 `--rebuild`는 새 폴더에 생성합니다.
모델 생성에는 Windows, CATIA V5, pywin32가 필요합니다. 이번 작업에서는 CATIA를 실행하지 않았습니다.

1~4번 사용자 설정을 적용하려면 해당 기기를 포함하는 명령에 `--vbk-config station1_config.json`,
`--so-config station2_config.json`, `--crp-config station3_config.json`, `--ms-config station4_config.json`을 추가합니다.
설정 파일이 있을 때만 해당 옵션을 붙이세요. 설정을 생략하면 코드 기본값을 사용합니다.
`README` 폴더의 이전 기기별 문서는 과거 기록이며 현재 실행 기준은 `README_RUN_01_12.md`입니다.

생성물 정리 옵션을 추가했습니다. `py build_line.py --clean --dry-run`은 미리보기,
`py build_line.py --clean`은 모델·리포트·모델 ZIP 실제 삭제입니다.
`--clean models`와 `--clean reports`로 범위를 나눌 수 있습니다. `clean_outputs.py`를 함께 보관하세요.
소스·설정·백업·사용자 문서는 보존합니다.

5번의 18번째 `Lower_Discharge_Cone`에서 발생한 Shaft Update 오류에 대해
스케치 회전축 등록(`CenterLine`)과 축 구속을 수정했습니다.

12번은 원본의 프로파일·브라켓 구조를 유지했으며 강도·전력 검토는 미확정입니다.
5→6번에는 받이 슈트, 폭 440 mm의 Z150 저상 벨트, 경사 벨트와 지지대를 생성합니다.
5번의 하부 가로보 밑으로 −Y 측면 인출 후 상승하며 6번 이후도 90° 돌려 배치합니다.
4번 제외 옵션은 번호를 유지한 채 3→5번을 직접 연결합니다. 기존 4번 CAD와 리뷰는 보존합니다.
신규 연결부는 첫 조립 때 생성하고 저장합니다. 전체 조립은 `Potato_Line_01_12_No04`에 저장합니다.
`transfer_05_06.py`를 포함해 이 폴더의 모든 Python 파일이 필요합니다.

본 프로젝트의 코드는 생성형 AI에 의해 생성되었습니다.
