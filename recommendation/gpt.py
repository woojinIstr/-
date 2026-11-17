
import os
from openai import OpenAI
from .engine import recommend


def recommend_with_gpt(workspace, user_request="오늘 저녁 추천해 줘"):
    # 기존 C 코드로 실제 재고에 맞는 메뉴 후보 찾기
    candidates = recommend(workspace, limit=5)

    if not candidates:
        return {
            "source": "rules",
            "message": "추천 가능한 메뉴가 없습니다.",
            "recommendations": []
        }

    # API 키는 서버의 환경변수에서만 읽기
    if not os.getenv("OPENAI_API_KEY"):
        return {
            "source": "rules",
            "message": "GPT 연결 전입니다. 기본 추천을 표시합니다.",
            "recommendations": candidates
        }

    try:
        client = OpenAI(timeout=15.0, max_retries=1)

        # GPT에게 보낼 메뉴 후보
        menu_text = "\n".join(
            f"{i+1}. {item['name']} / "
            f"조리시간 {item['minutes']}분 / "
            f"{item['reason']}"
            for i, item in enumerate(candidates)
        )

        response = client.responses.create(
            model="gpt-6-luna",
            instructions=(
                "당신은 다음한끼의 요리 추천 도우미입니다. "
                "제공된 메뉴 후보 중에서만 추천하세요. "
                "없는 재료나 조리 가능 여부를 지어내지 마세요. "
                "한국어로 짧고 친절하게 추천 이유를 설명하세요. "
                "재료 안전성, 알레르기, 영양을 검증했다고 주장하지 마세요."
            ),
            input=(
                f"사용자 요청: {user_request}\n"
                f"추천 가능한 메뉴 후보:\n{menu_text}\n"
                "가장 적절한 메뉴 1~2개와 추천 이유를 알려주세요."
            ),
            max_output_tokens=300,
            store=False
        )

        return {
            "source": "gpt",
            "message": response.output_text,
            "recommendations": candidates
        }

    except Exception:
        # GPT가 실패해도 기존 추천 기능 유지
        return {
            "source": "rules",
            "message": "AI 연결이 원활하지 않아 기본 추천을 표시합니다.",
            "recommendations": candidates
        }
