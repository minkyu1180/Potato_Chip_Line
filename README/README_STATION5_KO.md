# 5번 BSM-150 — R13 용접 프레임·계산서

`station5_bsm150.py`는 사용자가 제공한 `5.py`를 기반으로 합니다. 주요 기구와 CATPart 10개 구성은 유지하고,
주 프레임 50 mm 사각관과 벨트 기둥 40 mm 사각관의 실제 벽 두께를 4 mm로 맞췄습니다.
다리·벨트 기둥 단부에 밀폐 캡을 추가했습니다. 현재 파일은 최초 원본과 동일하지 않습니다.

이 폴더의 Python 파일 7개를 함께 두고 `build_line.py`로 실행하세요.
`station5_bsm150.py` 직접 실행은 통합 계산서·재사용 관리 경로를 거치지 않습니다.

```powershell
py build_line.py --stage 5 --report-only --finish-config finishing_config.json
py build_line.py --stage 5 --rebuild --finish-config finishing_config.json
```

기본값: BSM-150 / CORRUGATED / 절단 두께 3 mm / 칼날 2개 / 제품 높이 60 mm.
절단 두께는 `--slice-thickness 3` 또는 `finishing_config.json`의 `5.slice_thickness_mm`에서
3·4·5·6 mm 중 선택합니다. 제품 높이는 원본 모듈의 `PRODUCT_H`와 같아야 합니다.

출력은 `build_line.py` 옆 `05_BSM_150_BeltSlicer` 폴더입니다.
이미 폴더가 있으면 새 번호 폴더를 만들며, 같은 완성 모델은 재사용합니다. 강제 새 생성은 `--rebuild`, ZIP 저장은 `--zip`입니다.
원본의 CATPart 10개와 CATProduct 구성을 유지하며, `--all`과 `--assemble`에서도 새 5번을 사용합니다.
조립 연결 좌표만 새 모델 기준 투입 Z1050, 배출 Z850으로 반영했습니다.

원본이 보고한 실패 단계가 있으면 `MODEL_INFO.json`의 `failed_steps`에 남기고 전체 공정을 중단합니다.
부분 생성 모델은 완성 모델로 재사용하지 않습니다.

계산서는 `05_BSM_Design_Review/05_BSM_Design_Review.html`입니다.
외형 1875×720×1395 mm는 공급사 공칭값이며 실제 생성 모델 외접치수 측정값이 아닙니다.
원제품의 230 V 단상/2.25 kW와 본 설계의 380 V 3상 요구사양을 구분했습니다.
잠정 나이프 모터 5.5 kW·벨트 모터 각 0.18 kW는 절단력·기동 가정에 따른 구매요구입니다.
모터 구매 외형과 기존 장착부의 적합성은 미확정으로 리뷰에 명시했습니다.
기타 기계 질량 210 kg, 평균 절단 접촉률 15%도 명시적 가정입니다. CATIA는 실행하지 않았습니다.
