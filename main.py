import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process

# 1. .env 파일의 OPENAI_API_KEY 로드
load_dotenv()

# 2. 에이전트 정의
# 모델명을 지정하지 않으면 CrewAI는 기본적으로 gpt-4o를 사용합니다.
analyzer = Agent(
    role='ISO 25010 품질 분석 전문가',
    goal='target_apps/breakout_game.py 파일을 분석하여 ISO 25010 표준에 따른 품질 결함을 보고하라.',
    backstory="""너는 소프트웨어 품질 보증(QA) 분야의 최고 전문가야. 
    특히 ISO/IEC 25010 품질 모델을 기반으로 파이썬 Pygame 코드의 
    기능 적합성, 신뢰성, 성능 효율성을 분석하는 데 탁월한 능력이 있어.""",
    verbose=True,
    allow_delegation=False
)

# 3. 분석 작업 정의
analysis_task = Task(
    description="""
    1. target_apps/breakout_game.py 소스 코드를 읽고 분석하라.
    2. ISO 25010의 '기능 정확성' 관점에서 물리 연산(충돌 로직)을 검토하라.
    3. '성능 효율성' 관점에서 게임 루프의 자원 관리(FPS 등)를 검토하라.
    """,
    expected_output="각 품질 지표별 결함 원인과 구체적인 개선 방향이 담긴 기술 보고서",
    agent=analyzer
)

# 4. 크루 설정 및 실행
qa_crew = Crew(
    agents=[analyzer],
    tasks=[analysis_task],
    process=Process.sequential
)

if __name__ == "__main__":
    print("### [GPT-4o] 에이전트 기반 품질 분석 시작 ###")
    try:
        result = qa_crew.kickoff()
        print("\n\n" + "="*50)
        print("최종 분석 보고서")
        print("="*50)
        print(result)
    except Exception as e:
        print(f"\n에러 발생: {e}")