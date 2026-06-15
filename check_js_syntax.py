# -*- coding: utf-8 -*-
import sys

def check_js_brackets(filepath):
    try:
        content = open(filepath, 'r', encoding='utf-8').read()
    except Exception as e:
        print(f"파일을 읽을 수 없습니다: {e}")
        return

    stack = []
    brackets = {
        '{': '}',
        '[': ']',
        '(': ')'
    }
    reverse_brackets = {v: k for k, v in brackets.items()}
    
    lines = content.split('\n')
    in_string = False
    string_char = None
    in_comment = False
    in_line_comment = False
    
    for line_idx, line in enumerate(lines, 1):
        i = 0
        in_line_comment = False
        while i < len(line):
            char = line[i]
            
            # 주석 및 문자열 내부 예외 처리
            if not in_comment and not in_line_comment and not in_string:
                if line[i:i+2] == '//':
                    in_line_comment = True
                    break
                elif line[i:i+2] == '/*':
                    in_comment = True
                    i += 2
                    continue
                elif char in ["'", '"', '`']:
                    in_string = True
                    string_char = char
                    i += 1
                    continue
            elif in_comment:
                if line[i:i+2] == '*/':
                    in_comment = False
                    i += 2
                else:
                    i += 1
                continue
            elif in_string:
                # 이스케이프 문자 예외 처리
                if char == '\\' and i + 1 < len(line):
                    i += 2
                    continue
                elif char == string_char:
                    in_string = False
                    i += 1
                    continue
                else:
                    i += 1
                    continue

            # 실제 괄호 검사
            if char in brackets:
                stack.append((char, line_idx, i, line))
            elif char in reverse_brackets:
                if not stack:
                    print(f"오류: 닫는 괄호 '{char}'가 {line_idx}행 {i}열에서 짝 없이 나타났습니다.")
                    print(f" 라인: {line.strip()}")
                    return False
                top_char, top_line, top_col, top_line_content = stack.pop()
                if brackets[top_char] != char:
                    print(f"오류: {top_line}행 {top_col}열의 '{top_char}' 괄호가 {line_idx}행 {i}열의 '{char}'와 맞지 않습니다.")
                    print(f" 여는 라인: {top_line_content.strip()}")
                    print(f" 닫는 라인: {line.strip()}")
                    return False
            i += 1
            
    if stack:
        print(f"오류: {len(stack)}개의 괄호가 닫히지 않고 파일이 끝났습니다.")
        for top_char, top_line, top_col, top_line_content in reversed(stack[:5]):
            print(f" - {top_line}행 {top_col}열의 '{top_char}'가 닫히지 않음: {top_line_content.strip()[:60]}...")
        return False
        
    print("성공: 모든 괄호 쌍이 완전히 일치합니다!")
    return True

if __name__ == '__main__':
    check_js_brackets('app.js')
