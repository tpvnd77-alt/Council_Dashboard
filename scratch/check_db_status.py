import os
import datetime
import sys

sys.stdout.reconfigure(encoding='utf-8')

db_path = "data/meetings.json"
if os.path.exists(db_path):
    mtime = os.path.getmtime(db_path)
    dt = datetime.datetime.fromtimestamp(mtime)
    print(f"data/meetings.json exists.")
    print(f"Last modified: {dt.isoformat()}")
    print(f"Current time: {datetime.datetime.now().isoformat()}")
    # check time difference
    diff = datetime.datetime.now() - dt
    print(f"Time since last modification: {diff.total_seconds()} seconds")
else:
    print("data/meetings.json does not exist!")
