import os

def find_references():
    scratch_dir = r"C:\Users\hp\.gemini\antigravity\scratch"
    print("Searching for 'bills_council' references:")
    for root, dirs, files in os.walk(scratch_dir):
        # Skip pycache and .git
        if '__pycache__' in root or '.git' in root:
            continue
        for f in files:
            if f.endswith('.py') or f.endswith('.bat'):
                path = os.path.join(root, f)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as file:
                        content = file.read()
                        if 'bills_council' in content:
                            rel_path = os.path.relpath(path, scratch_dir)
                            print(f"  File: {rel_path}")
                except Exception:
                    pass

if __name__ == '__main__':
    find_references()
