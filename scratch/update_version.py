with open('index.html', 'r', encoding='utf-8') as f:
    text = f.read()

# 버전 v=3.7을 v=3.8으로 치환
text = text.replace('v=3.7', 'v=3.8')

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(text)

print("index.html upgraded successfully to v=3.8")
