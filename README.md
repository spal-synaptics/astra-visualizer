# Visualize Resource Usage on Astra SL Boards

## Setup
```
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
```

## Dashboard
```
python3 -m src.dashboard <board IP>
```

#### Run Options
* `-i/--interval`: Polling interval in milliseconds (default: 500 ms)
* `-w/--window`: Statistics sliding window length in seconds (default: 10 s)
* `--port`: Port for running display dashboard webapp (default: 8050)
