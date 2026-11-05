# 생성 모델·리포트 정리 옵션 — 2026-11-05

`build_line.py`와 `clean_outputs.py`를 같은 폴더에 두세요. 다음 명령은 CATIA를 실행하지 않으며,
기본 대상은 현재 터미널 위치가 아니라 **build_line.py가 있는 폴더**입니다.

```powershell
# 삭제 대상 미리보기: 파일 변경 없음
py build_line.py --clean --dry-run

# 생성된 모델·리포트·모델 ZIP 실제 삭제
py build_line.py --clean

# 모델만 정리: CATPart/CATProduct/STEP/모델 ZIP
py build_line.py --clean models

# 리포트만 정리: HTML·계산 JSON·생성 CSV·리뷰 목록
py build_line.py --clean reports

# 다른 생성 출력 폴더를 지정하는 예
py build_line.py --clean --output-dir "D:\Potato_Output" --dry-run
```

`--clean`과 `--clean all`은 같습니다. `--clean models --dry-run`, `--clean reports --dry-run`도 가능합니다.
`--clean`은 정리 후 종료합니다. 생성 명령인 `--stage`, `--stages`, `--all`, `--assemble`,
`--report-only`, `--rebuild` 등과 함께 사용할 수 없습니다.

## 정리 범위

- `MODEL_INFO.json`으로 확인된 생성 모델 폴더의 CATPart·CATProduct·STEP와 생성 메타데이터.
- 앞으로 생성하는 폴더는 `.potato_line_generated.json` 표시를 먼저 남겨, 중간에 끊긴 모델도 식별합니다.
- 프로젝트의 정해진 리뷰 폴더와 리포트 파일명. 현재 5번 CC 리뷰·BOM·가공/용접 CSV도 포함합니다.
- 내부 생성 기록과 CAD 파일이 확인되는 모델 ZIP. Python 소스 등 다른 파일이 들어 있는 ZIP은 보존합니다.
- 삭제 후 비게 된 하위 폴더. 사용자가 추가한 파일이 있으면 해당 폴더는 남습니다.
- `BUILD_STATUS.json`에서는 이 출력 폴더 안의 삭제되거나 이미 없어진 생성 모델 기록만 정리합니다.

Python 코드·코드 백업·README·루트의 `station*_config.json` 및 `finishing_config.json`은 보존합니다.
출처를 확인할 수 없는 폴더, 별도 사용자 파일, 심볼릭 링크·Windows junction은 삭제하지 않습니다.
생성 모델 폴더의 `Parts`, `CATParts`, `Subassemblies` 안 CAD 파일은 해당 모델의 구성 파일로 취급합니다.
그 안에서 직접 수정한 CAD도 모델 정리를 실행하면 삭제 대상이 됩니다.
5번 모델 폴더의 `05_Config.json`은 생성 시 저장한 설정 스냅샷이므로 모델 정리 대상입니다.

`--clean models`에서는 남겨 둔 리포트를 다음 정리 때도 찾을 수 있도록 일부 모델 식별 기록이 남을 수 있습니다.
`--clean reports`에서는 CAD가 포함된 모델 ZIP을 그대로 둡니다.
열려 있거나 잠긴 파일, 정리 계획 이후 바뀐 파일은 오류를 출력하고 보존합니다. 오류가 있으면 종료 코드는 1입니다.
이 옵션의 삭제는 휴지통 이동이 아닌 파일 삭제입니다. 먼저 미리보기로 범위를 확인할 수 있습니다.

## 다시 생성

정리 후 원하는 생성 명령을 별도로 실행합니다. 예:

```powershell
py build_line.py --stages 5 6 7 8 9 10 11 --finish-config finishing_config.json
```

이번 기능 추가 작업에서는 실제 출력물을 지우지 않았습니다. 삭제 동작은 임시 테스트 폴더에서만 확인했습니다.
