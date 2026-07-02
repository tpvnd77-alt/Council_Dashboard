import os
import sys

def main():
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    print("=====================================================")
    print("       국회 회의록 대시보드 - 새로운 Gemini API 키 등록")
    print("=====================================================")
    print()
    try:
        new_key = input("새로 발급받은 Gemini API 키를 입력하세요 (예: AIzaSy...): ").strip()
    except KeyboardInterrupt:
        print("\n취소되었습니다.")
        return
        
    if not new_key:
        print("입력된 값이 없습니다. 종료합니다.")
        return
        
    if not new_key.startswith("AIzaSy"):
        print("경고: 올바른 Gemini API 키 형식이 아닌 것 같습니다. (AIzaSy로 시작해야 합니다.)")
        try:
            confirm = input("그래도 진행하시겠습니까? (y/n): ").strip().lower()
        except KeyboardInterrupt:
            print("\n취소되었습니다.")
            return
        if confirm != 'y':
            print("취소되었습니다.")
            return

    env_path = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\.env"
    lines = []
    updated = False
    
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        lines.append(f'GEMINI_API_KEY="{new_key}"\n')
                        updated = True
                    else:
                        lines.append(line)
        except Exception as e:
            print(f"기존 .env 파일을 읽는 중 오류 발생: {e}")
            
    if not updated:
        lines.append(f'GEMINI_API_KEY="{new_key}"\n')
        
    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print()
        print("성공: 새로운 API 키가 .env 파일에 안전하게 저장되었습니다!")
        print("이제 대시보드와 자동 파싱 시스템이 새 키로 정상 동작합니다.")
    except Exception as e:
        print(f".env 파일 작성 중 오류 발생: {e}")
        
    print("=====================================================")
    try:
        input("아무 키나 누르면 종료됩니다...")
    except Exception:
        pass

if __name__ == "__main__":
    main()
