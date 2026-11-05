# 5번 CC 슬라이서 Shaft·PartNumber 수정 — 2026-11-05

`SAVED MASTER 17/109: Chamber_Support_Ring`은 17번 부품의 저장 완료 기록입니다.
그다음 **18번 S05CC_P018 / Lower_Discharge_Cone**의 Shaft Update에서 실패했습니다.

`build_catia.py`의 회전 형상 생성 함수를 수정했습니다.

- 닫힌 4변 단면과 XZ 지지 평면을 유지합니다.
- 스케치 편집 중 회전선을 `Sketch.CenterLine`에 등록한 다음 Shaft를 생성합니다.
- 회전축 양 끝점을 좌표로 구속하고 보조점·보조선으로 지정합니다.
- 이미 단면에 벽 두께가 있으므로 Thin 모드는 끄고 회전 범위를 360°/0°로 지정합니다.
- 같은 함수를 사용하는 `Lower_Discharge_Cone`, `Swing_Away_Cutting_Cover`, `Infeed_Hopper_D465`에 적용됩니다.
- 부품 생성 전에 `BUILD MASTER 번호/총수: 이름`을 출력하고, `BUILD_STATUS.json`에 현재 부품을 기록합니다.
  실패 시 완료된 부품 수와 저장 위치를 포함한 오류를 출력하며 실패를 숨기지 않습니다.

이번 변경은 회전축 정의와 생성 절차를 수정한 것입니다. 원추의 치수·벽 두께·배치·계산 입력은 바꾸지 않았습니다.
Shaft 속성 및 스케치 회전축 근거:
[Dassault CAA Sketch.CenterLine 문서 미러](https://catiadesign.org/_doc/V5Automation/generated/interfaces/SketcherInterfaces/interface_Sketch_21197.htm),
[Dassault CAA Revolution 문서 미러](https://catiadesign.org/_doc/V5Automation/generated/interfaces/PartInterfaces/interface_Revolution_18204.htm).

현재 작업 폴더의 소스를 수정했으므로 다음 명령으로 5번을 다시 생성하세요.

```powershell
py build_line.py --stage 5 --rebuild --finish-config finishing_config.json
```

새 번호 폴더에 생성하며 기존 완료/부분 모델을 지우지 않습니다.
자동으로 18번부터 이어 만드는 기능은 아니며 5번 전체를 다시 생성합니다.
다른 컴퓨터로 옮길 때는 ZIP의 Python 모듈·설정 파일을 함께 보관하세요.

이후 재실행에서 발생한 `CATIAProduct: The method PartNumber failed`는 새 Part 번호를 지정하는 단계의 오류입니다.
해당 시도에서는 Shaft 생성 단계에 아직 도달하지 않았습니다. 이전 실패 문서 또는 세션에 남은 동일 이름과의
충돌 가능성을 피하도록 다음을 추가했습니다. 오류 메시지만으로 CATIA 내부 거부 원인을 확정한 것은 아닙니다.

- 실행마다 12자리 ID를 만들고 PartNumber와 CATPart/CATProduct 파일명에 붙입니다.
- 원래 부품 ID는 `Generator_Master_ID` 파라미터와 `BUILD_STATUS.json`에 남깁니다.
- Part 문서를 활성화하고 초기 Update를 마친 뒤 PartNumber를 지정합니다.
- 생성 실패 시 해당 호출이 방금 만든 문서만 닫습니다. 이미 열려 있던 사용자 문서는 닫지 않습니다.
- 통합 코드가 고정 파일명 대신 실제 저장된 `doc.FullName`을 MODEL_INFO에 기록하여 조립 링크를 유지합니다.
- 예: `S05CC_P018_Lower_Discharge_Cone_<실행ID>.CATPart`, `05_Urschel_CC_R15_<실행ID>.CATProduct`.

이름 충돌 참고:
[Dassault CATIA Naming or Renaming a Product 문서 미러](https://catia-v5-help.anarkia333data.center/online/pstug_C2/pstugbt0301.htm).

확인 범위: 단면·회전축 호출 순서 3개, 실행별 이름 분리·실패 문서 정리·실제 저장 경로 연결 4개.
실제 CATIA 커널 실행은 하지 않았습니다.
생성물 정리 옵션도 포함되며 사용법은 `README_CLEANUP_KO.md`를 참조하세요.
