@echo off
REM Sends the once-a-day MOC email digest. Register via Windows Task Scheduler
REM to run once daily (e.g. 23:30) so it covers the whole day's sync activity -
REM the command itself refuses to send twice in the same calendar day.
cd /d "C:\Users\Canton Computers\Desktop\Debt Criteria check"
"C:\Users\Canton Computers\AppData\Local\Programs\Python\Python312\python.exe" manage.py send_moc_daily_digest
