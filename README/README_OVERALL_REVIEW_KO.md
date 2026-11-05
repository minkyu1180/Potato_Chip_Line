# 전체 디자인 리뷰 · R18 / 2026-11-06

시작 파일은 `Overall_Review/01_11_Design_Review_Index.html`입니다. 1~11번 기기 이름을 누르면 개별 리뷰가 열립니다.
리뷰는 5번과 같은 순서로 크기·구조, 하중·안전한계, 처리량·속도, 모터·전기요금, 부품·가격, 제작 공임을 정리합니다.
긴 계산 조건과 BOM은 펼쳐보기로 두고, 전체 계산값은 JSON에 남깁니다. 견적이나 실측값이 없으면 미확정으로 표시합니다.

## 파일 구조

```text
Potato_Line_Native_R3/
  build_line.py / build_catia.py / 나머지 Python 모듈
  station1_config.json ... station4_config.json / finishing_config.json
  Overall_Review/
    01_11_Design_Review_Index.html
    01_11_Review_Summary.json
    05_to_06_Connection_Concept.html / .json
    BUILD_STATUS.json
    README_KO.md
    01_VBK_Design_Review/ ... 11_SD_Design_Review/
    Legacy_Reports/   과거 5~11번 목록 및 충돌 시 보존한 구버전
  01_.../ ... 11_.../  개별 모델 폴더: CATPart/CATProduct/그 모델의 계산서·MODEL_INFO
```

코드 폴더에 있던 기존 리뷰 폴더·5~11번 목록·생성 상태 기록은 다음 실행 때 `Overall_Review`로 옮깁니다.
같은 위치에 서로 다른 파일이 있으면 과거 파일은 `Legacy_Reports`에 보관합니다.
개별 모델 폴더와 사용자가 추가한 파일은 이동하지 않습니다.
`--output-dir`를 지정하면 그 출력 폴더 아래에 `Overall_Review`가 생깁니다.

## 입력 JSON은 보관

`station3_config.json` 같은 설정 파일은 생성물이 아닙니다. `--crp-config station3_config.json`을 붙였을 때 읽는 입력입니다.
설정 옵션을 생략하면 코드의 기본값을 사용합니다. 삭제해도 기본 실행은 가능하지만 저장한 설정값은 사라집니다.
이 입력 파일들은 Python 코드 옆에 보관합니다. 단, 모델 폴더 안 `05_Config.json`은 생성 시 남긴 입력 스냅샷입니다.

## 실행

```powershell
# 전체 리뷰 생성 — CATIA 실행 없음, 각 리뷰 저장 직후 목록 갱신
py build_line.py --all --report-only --finish-config finishing_config.json

# 1~4번 저장 설정까지 적용한 전체 리뷰
py build_line.py --all --report-only --vbk-config station1_config.json --so-config station2_config.json --crp-config station3_config.json --ms-config station4_config.json --finish-config finishing_config.json

# 5번 수정 모델 생성
py build_line.py --stage 5 --rebuild --finish-config finishing_config.json

# 생성된 리뷰 정리 대상 확인
py build_line.py --clean reports --dry-run
```

## 5번 이번 변경

외부 감속기 케이스 시작을 X885 mm로 옮겨, 지지 링 최외곽 X864 mm와 21 mm 설계 여유를 둡니다.
모터·수평축 중심은 Z700 mm로 맞추고, 원추 판에는 실제 Ø70 관통 구멍을 만듭니다.
그 구멍에 고정 밀폐 보호관 Ø70×3 mm를 연결하고 안쪽으로 Ø40 구동축이 지나갑니다.
내부 직각 구동부와 외부 감속기를 구분했으며 구매 기어·씰·정비 구조의 상세 확정은 별도 항목입니다.
모터 받침과 감속기 선반 지지도 새 높이에 맞췄습니다. 원추·원통 질량 계산은 이 작은 관통 구멍 체적을
차감하지 않은 보수적인 형상 질량이며, 실제 제작 질량은 CAD 질량 또는 구매 도면으로 교체합니다.

## 5→6번 연결

현재 5번은 Z500 mm 아래 방향 배출, 6번은 Z1200 mm 수평 투입입니다.
별도 문서 `05_to_06_Connection_Concept.html`에 측면 받이와 경사 컨베이어, 5번 받침 증고안을 정리했습니다.
아이디어 단계이며 이번 CAD와 자동 어셈블리에는 반영하지 않았습니다. 현재 자동 조립의 +X 직선 연결을
최종 연결로 사용하려면 먼저 하향 배출·프레임 여유·방향 전환을 반영한 Transfer_05_06 설계가 필요합니다.

## 수치 읽는 법

현재 1~4번의 설계 운전점과 5~11번 운전 유량이 다릅니다. 앞단 kg/h를 완제품 kg/h로 그대로 읽지 않습니다.
5번 실제 전기입력은 미측정이므로 전체 소비전력·비용을 확정 합계로 표시하지 않습니다.
각 기기의 가정과 한계, 출처를 확인하세요. 이번 수정은 Python 형상·리뷰 코드이며 CATIA 실행 검증은 사용자 수행입니다.
