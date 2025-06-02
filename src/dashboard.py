import argparse
import time
import threading
from collections import deque

from dash import Dash, dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go

from .remote import remote_command_runner_factory, RemoteCommandError


class SystemProfiler:
    
    def __init__(self, board_address, history_length=100, interval_ms=500):
        self.cmd_runner = remote_command_runner_factory(board_address)
        self.history_length = history_length
        self.interval_s = interval_ms / 1000

        self.previous_stats: dict = {}

        self.cpu_time_points = deque(maxlen=history_length)
        self.cpu_usage_history = {}
        self.npu_usage_history = deque(maxlen=history_length)

        self.lock = threading.Lock()
        self._start_polling_thread()
    
    @staticmethod
    def parse_stats(raw: str) -> dict[str, list[int]]:
        stats = {}
        raw_data = raw.strip().splitlines()
        for line in raw_data:
            if line.startswith("cpu"):
                parts = line.split()
                stats[parts[0]] = list(map(int, parts[1:]))
        stats["infer_time_us"] = int(raw_data[-1])
        return stats

    @staticmethod
    def compute_cpu_usage(prev_stats: dict, curr_stats: dict) -> dict[str, float]:
        usage = {}
        for proc in prev_stats:
            if "cpu" in proc:
                prev, curr = prev_stats[proc], curr_stats[proc]
                total = sum(c2 - c1 for c1, c2 in zip(prev, curr))
                idle = (curr[3] + curr[4]) - (prev[3] + prev[4])
                usage[proc] = 100.0 * (1 - idle / total) if total > 0 else 0.0
        return usage

    def _start_polling_thread(self):
        def poll_loop():
            while True:
                try:
                    raw_stats: str = self.cmd_runner.run_cmd("cat /proc/stat && cat /sys/class/misc/synap/statistics/inference_time")
                except RemoteCommandError as e:
                    raise RuntimeError(f"Failed to fetch system stats: {e}\n\nPress Ctrl + C to exit") from e
                curr_stats = self.parse_stats(raw_stats)
                curr_ts = time.time()

                if self.previous_stats:
                    time_delta_s = curr_ts - self.previous_stats["ts"]
                    cpu_usage = self.compute_cpu_usage(self.previous_stats, curr_stats)
                    npu_usage = 100.0 * (curr_stats["infer_time_us"] - self.previous_stats["infer_time_us"]) / (time_delta_s * 1_000_000)
                    npu_usage = min(max(0.0, npu_usage), 100.0)
                    with self.lock:
                        self.cpu_time_points.append(curr_ts)
                        for cpu, val in cpu_usage.items():
                            if cpu not in self.cpu_usage_history:
                                self.cpu_usage_history[cpu] = deque(maxlen=self.history_length)
                            self.cpu_usage_history[cpu].append(val)
                        self.npu_usage_history.append(npu_usage)

                self.previous_stats.clear()
                self.previous_stats.update(curr_stats)
                self.previous_stats["ts"] = curr_ts

                time.sleep(self.interval_s)

        threading.Thread(target=poll_loop, daemon=True).start()

    def get_cpu_history(self):
        with self.lock:
            return list(self.cpu_time_points), {
                cpu: list(vals) for cpu, vals in self.cpu_usage_history.items()
            }

    def get_npu_history(self):
        with self.lock:
            return list(self.cpu_time_points), list(self.npu_usage_history)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-b", "--board-address", 
        type=str, 
        default=None,
        help="ADB device ID (wired USB connection) or SSH address (wireless connection) (default: None, uses first detected ADB device)"
    )
    parser.add_argument(
        "-i", "--interval", 
        type=int, 
        metavar="MILLISECONDS", 
        default=500, 
        help="Polling interval in milliseconds (default: %(default)s)"
    )
    parser.add_argument(
        "-w", "--window", 
        type=int, 
        metavar="SECONDS", 
        default=10, 
        help="Statistics sliding window length in seconds (default: %(default)s)"
    )
    parser.add_argument(
        "--port",
        type=int, 
        default=8050, 
        help="Port for running display webapp (default: %(default)s)"
    )
    args = parser.parse_args()

    # === Dash App ===
    profiler = SystemProfiler(args.board_address, interval_ms=args.interval)

    app = Dash(__name__)
    app.title = "Live Resource Usage"

    app.layout = html.Div([
        html.H2("Live Resource Usage Monitor"),
        html.Div([
            dcc.Graph(id="cpu-usage-graph"),
            dcc.Graph(id="npu-usage-graph")
        ]),
        html.Div(id="cpu-stats-text", style={"fontFamily": "monospace", "whiteSpace": "pre"}),
        dcc.Interval(id="update-timer", interval=args.interval, n_intervals=0),
    ], style={"padding": "2rem"})

    @app.callback(
        Output("cpu-usage-graph", "figure"),
        Output("npu-usage-graph", "figure"),
        Output("cpu-stats-text", "children"),
        Input("update-timer", "n_intervals")
    )
    def update_graph_and_text(_):
        window_s = args.window
        cpu_times, cpu_data = profiler.get_cpu_history()
        npu_times, npu_data = profiler.get_npu_history()

        if not cpu_times:
            return go.Figure(), go.Figure(), ""

        now = cpu_times[-1]
        start_time = now - window_s

        def filter_series(times, values):
            return [(t, v) for t, v in zip(times, values) if t >= start_time]

        cpu_traces = []
        npu_traces = []
        cpu_text = []

        # CPU
        for cpu, values in cpu_data.items():
            filtered = filter_series(cpu_times, values)
            if not filtered:
                continue
            x_vals, y_vals = zip(*filtered)
            x_vals = [x - start_time for x in x_vals]
            line = {"dash": "dot", "width": 5} if cpu == "cpu" else None
            opacity = 1.0 if cpu == "cpu" else 0.65
            cpu_traces.append(go.Scatter(x=x_vals, y=y_vals, mode='lines', name=cpu, opacity=opacity, line=line))
            cpu_text.append(f"{cpu:>5}: {y_vals[-1]:5.1f}%")

        # NPU
        if npu_data:
            filtered = filter_series(npu_times, npu_data)
            if filtered:
                x_vals, y_vals = zip(*filtered)
                x_vals = [x - start_time for x in x_vals]
                npu_traces.append(go.Scatter(x=x_vals, y=y_vals, mode='lines', name="NPU", line = {"width": 3}))
                cpu_text.append(f"  NPU: {y_vals[-1]:5.1f}%")

        cpu_fig = go.Figure(data=cpu_traces)
        cpu_fig.update_layout(
            title="CPU Usage",
            xaxis=dict(visible=False),
            yaxis=dict(title="Usage (%)", range=[0, 100]),
            legend=dict(orientation="h")
        )

        npu_fig = go.Figure(data=npu_traces)
        npu_fig.update_layout(
            title="NPU Usage",
            xaxis=dict(visible=False),
            yaxis=dict(title="Usage (%)", range=[0, 100]),
            legend=dict(orientation="h")
        )

        return cpu_fig, npu_fig, "\n".join(cpu_text)


    app.run(debug=True, host="localhost", port=args.port)
