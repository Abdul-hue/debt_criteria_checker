@echo off
cd /d "C:\Users\Canton Computers\Desktop\Debt Criteria check"
"C:\Users\Canton Computers\AppData\Local\Programs\Python\Python312\python.exe" manage.py sync_creditor_vote_summaries --log-file "C:\Users\Canton Computers\Desktop\Debt Criteria check\creditor_vote_sync.log"
