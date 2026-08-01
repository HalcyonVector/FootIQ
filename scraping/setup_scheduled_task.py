"""
Registers (or re-registers) the Windows Scheduled Task that runs
auto_update.py weekly. Run this once to set it up:

    python scraping/setup_scheduled_task.py

Re-run any time (e.g. after changing the day/time constants below) to
update the existing registration -- it deletes and recreates the task by
name, so it's always safe to re-run.

Covers, specifically:
  - Weekly cadence (default: Monday 03:00 local time -- change DAY/TIME below)
  - No visible window ever: launches pythonw.exe (the windowless Python
    launcher) directly, not python.exe, so there's no console to flash even
    momentarily. auto_update.py itself never shells out to another
    python.exe either (it imports scrape()/main() directly), so there's no
    second process that could pop a window.
  - Catches up if missed: <StartWhenAvailable> -- if the PC was off/asleep
    at the scheduled time, it runs as soon as the PC is next on, rather than
    silently skipping that week.
  - AC power only: <DisallowStartIfOnBatteries> (won't start on battery) and
    <StopIfGoingOnBatteries> (aborts if unplugged mid-run).
  - Survives screen lock/sleep during the run (<LogonType>S4U</LogonType>) --
    S4U runs independent of the interactive session (no stored password
    needed, unlike "run whether user is logged on or not" which requires
    Task Scheduler to store your Windows password). InteractiveToken was
    tried first and found to hard-kill the process (Task Scheduler result
    -2147023829) if the screen locked/slept mid-run, since it ties the
    process to the interactive session's lifetime -- a real problem for a
    job that can run 20-60+ minutes unattended.
"""
import getpass
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PYTHONW = Path(r"C:\Users\basus\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe")
AUTO_UPDATE_SCRIPT = Path(__file__).parent / "auto_update.py"

TASK_NAME = "FootIQ Weekly Data Refresh"
DAY = "Monday"     # Monday/Tuesday/Wednesday/Thursday/Friday/Saturday/Sunday
TIME = "03:00"     # 24h local time, HH:MM

XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Weekly: scrape current-season FootIQ data, rebuild parquet, commit and push if changed. See scraping/auto_update.py.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start_boundary}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <DaysOfWeek>
          <{day}/>
        </DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user_id}</UserId>
      <LogonType>S4U</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>true</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{pythonw}</Command>
      <Arguments>"{script}"</Arguments>
      <WorkingDirectory>{cwd}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def main():
    if sys.platform != "win32":
        print("This registers a Windows Scheduled Task; not applicable on this OS.")
        return

    if not PYTHONW.exists():
        print(f"ERROR: {PYTHONW} not found — update the PYTHONW path in this script.")
        return

    user_id = rf"{os.environ.get('USERDOMAIN', '')}\{getpass.getuser()}"
    start_boundary = f"2026-01-05T{TIME}:00"  # any past Monday works — CalendarTrigger only uses the time-of-day + weekly recurrence

    xml = XML_TEMPLATE.format(
        start_boundary=start_boundary,
        day=DAY,
        user_id=user_id,
        pythonw=str(PYTHONW),
        script=str(AUTO_UPDATE_SCRIPT),
        cwd=str(REPO_ROOT),
    )

    xml_path = Path(__file__).parent / "_scheduled_task.xml"
    xml_path.write_text(xml, encoding="utf-16")

    # Delete any existing registration first so re-running this is always safe.
    subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True)

    result = subprocess.run(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path)],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print("ERROR registering task:")
        print(result.stderr)
        return

    print(f"Registered '{TASK_NAME}': every {DAY} at {TIME}, AC power only, "
          f"catches up if missed, no visible window.")
    print("Verify any time with: schtasks /Query /TN \"FootIQ Weekly Data Refresh\" /V /FO LIST")
    print("Trigger a manual test run with: schtasks /Run /TN \"FootIQ Weekly Data Refresh\"")


if __name__ == "__main__":
    main()
