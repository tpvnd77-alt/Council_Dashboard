import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

log_path = r"C:\Users\hp\.gemini\antigravity\brain\34beea02-e022-4a3d-9fd0-a4c5ecc90505\.system_generated\tasks\task-2819.log"
print(f"Log path exists: {os.path.exists(log_path)}")
if os.path.exists(log_path):
    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    print(f"Total lines: {len(lines)}")
    print("Last 15 lines of log:")
    for line in lines[-15:]:
        print(line.strip())
else:
    print("Checking containing directory:")
    dir_path = os.path.dirname(log_path)
    if os.path.exists(dir_path):
        print(f"Files in {dir_path}:")
        for f in os.listdir(dir_path):
            print(f"  {f}")
    else:
        print(f"Directory {dir_path} does not exist!")
