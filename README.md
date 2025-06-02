# Visualize Resource Usage on Astra SL Boards
Monitor resource utilization on Astra SL boards via USB (ADB) or network (SSH).

## Prerequisites
* Python 3.8+
* `adb` and/or SSH access to the board
* Astra SL board connected via USB or network

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
```

## Run Dashboard
ADB (USB):
```bash
source .venv/bin/activate
python3 -m src.dashboard
```

SSH:
```bash
source .venv/bin/activate
python3 -m src.dashboard -b <board IP>
```
> [!NOTE]  
> To ensure successful SSH host-key verification, connect to **new** board IP's with `ssh root@<board IP>` before running dashboard.

#### Run Options
* `-b/--board-address`: ADB device ID or IP address (for SSH). Defaults to connecting with first detected SL board via ADB if not provided.
* `-i/--interval`: Polling interval in milliseconds (default: 500 ms)
* `-w/--window`: Statistics sliding window length in seconds (default: 10 s)
* `--port`: Port for running display dashboard webapp (default: 8050)

Once started, you should see an output like:
```sh
Dash is running on http://localhost:8050/
...
```
Copy the URL and open in a new browser tab to view dashboard.

Enter `Ctrl + C` to stop dashboard.
