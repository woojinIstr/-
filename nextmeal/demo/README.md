# 다음한끼 시연 실행

운영 앱과 같은 제품 빌드를 이 컴퓨터에서 실행합니다. 시연에서는 임시 SQLite를 쓰며 계정과 API 키가 필요 없습니다. 실행 창을 닫으면 시연 데이터는 지워집니다.

## Windows

Python 3.12를 설치하고 명령 프롬프트에서 저장소의 `nextmeal/` 폴더로 이동한 뒤 실행합니다. 처음에는 의존성을 설치합니다.

```bat
demo\DEMO_WINDOWS.cmd --example
```

인수 없이 실행하면 빈 냉장고로 시작합니다. 포트가 이미 사용 중이면 `--port 8001`을 추가합니다.

## macOS 및 Linux

저장소의 `nextmeal/` 폴더에서 실행합니다.

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/python demo/run.py --example
```

## 발표 화면 순서

1. **식사 계획**에서 오늘 저녁의 삼겹살 저녁을 외식으로 저장합니다.
2. 탭을 닫고 실행 창에 나온 주소를 다시 엽니다. 식사 계획의 **다음 집밥 고르기**를 클릭합니다.
3. **20분**, **있는 재료만**으로 내일 아침을 **달걀밥**으로 바꿉니다.
4. 미리보기에서 자동 양파 **200g → 0g**, 당근 **2개 유지**, 직접 적은 양파 **70g 유지**를 확인합니다.
5. **이대로 적용**하고 장보기에도 같은 변화가 표시되는지 보여 줍니다. 조리 완료는 필요할 때 시연합니다.
