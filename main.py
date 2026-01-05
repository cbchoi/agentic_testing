import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from tools.file_tools import ReadFileTool, WriteFileTool, ExecuteScriptTool

# 1. .env 파일의 OPENAI_API_KEY 로드
load_dotenv()

# 2. 에이전트 정의
# 모델명을 지정하지 않으면 CrewAI는 기본적으로 gpt-4o를 사용합니다.
# 에이전트 정의 (도구 추가 버전)
analyzer = Agent(
    role='ISO 25010 품질 분석 및 자동화 테스트 전문가',
    goal='코드를 분석하고 테스트하여, 발견된 결함을 한국어 보고서로 작성하라.',
    backstory="""너는 소프트웨어 품질 전문가야. 모든 분석 과정과 최종 보고서는 
    반드시 한국어로 작성해야 하며, 전문 용어는 ISO 25010 표준을 따른다.
    사용자가 이해하기 쉽게 결함의 원인과 영향을 상세히 설명하라.""",
    llm="gpt-4o",
    verbose=True,
    allow_delegation=False,
    tools=[ReadFileTool(), WriteFileTool(), ExecuteScriptTool()]
)

# 3. 분석 작업 정의
dynamic_test_task = Task(
    description="""
    1. 'read_file'을 사용하여 target_apps/breakout_game.py를 분석하라.
    2. 결함이 의심되는 곳에 'write_file'로 로그를 삽입하고 'execute_script'로 검증하라.
    3. 모든 검증이 끝나면 반드시 'write_file'로 코드를 원래 상태로 복구하라.
    4. 최종적으로 ISO 25010 기반의 품질 분석 결과 보고서를 한국어로 작성하라.
    """,
    expected_output="ISO 25010 기반의 상세 품질 분석 한국어 리포트 (Markdown 형식)",
    agent=analyzer,
    output_file='quality_analysis_report.md'
)

# 4. 크루 설정 및 실행
qa_crew = Crew(
    agents=[analyzer],
    tasks=[dynamic_test_task],
    process=Process.sequential
)

if __name__ == "__main__":
    print("### [GPT-4o] 한국어 품질 분석 에이전트 가동 ###")
    result = qa_crew.kickoff()
    print(f"\n\n### 분석 완료! 보고서가 저장되었습니다: quality_analysis_report.md")