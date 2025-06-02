import os
import subprocess
import shlex
import tempfile
from abc import ABC, abstractmethod


class RemoteCommandError(BaseException):

    def __init__(self, cmd: str, output: str):
        self.cmd = cmd
        self.output = output
        super().__init__(f"Error running command \"{cmd}\":\n\t{output}")


class BaseCommandRunner(ABC):

    @abstractmethod
    def run_cmd(self, cmd: str | list[str]) -> str | None:
        ...

    @abstractmethod
    def copy(self, src: str, dst: str, recursive: bool = False, board_dst: bool = False) -> None:
        ...


class ADBCommandRunner(BaseCommandRunner):

    def __init__(self, device_id: str | None = None, timeout: int = 5):
        super().__init__()
        self.device_id = device_id
        self.timeout = int(timeout)

    def _build_adb_cmd(self) -> list[str]:
        cmd = ["adb"]
        if self.device_id:
            cmd += ["-s", self.device_id]
        return cmd

    def run_cmd(self, cmd: str | list[str]) -> str | None:
        if isinstance(cmd, list):
            cmd = " ".join(shlex.quote(arg) for arg in cmd)

        if any(op in cmd for op in ['|', ';', '||', '`', '$(', '<', '>']):
            raise RemoteCommandError(cmd, "Unsupported shell syntax in ADB runner.")

        parts = [part.strip() for part in cmd.split("&&")]
        results = []

        for part in parts:
            full_cmd = self._build_adb_cmd() + ["exec-out"] + shlex.split(part)
            try:
                result = subprocess.check_output(
                    full_cmd,
                    timeout=self.timeout,
                    text=True,
                    stderr=subprocess.STDOUT
                )
                results.append(result)
            except subprocess.CalledProcessError as e:
                raise RemoteCommandError(' '.join(e.cmd), e.output) from e
            except subprocess.TimeoutExpired:
                raise RemoteCommandError(part, f"Command timed out after {self.timeout} seconds")

        return "\n".join(results)

    def copy(self, src: str, dst: str, recursive: bool = False, board_dst: bool = False) -> None:
        base_cmd = self._build_adb_cmd()
        if board_dst:
            cmd = base_cmd + ["push"]
            cmd += ["-r"] if recursive else []
            cmd += [src, dst]
        else:
            cmd = base_cmd + ["pull"]
            cmd += ["-a"]  # preserve timestamps if needed
            cmd += [src, dst]

        try:
            subprocess.check_output(
                cmd,
                timeout=self.timeout,
                stderr=subprocess.STDOUT,
                text=True
            )
        except subprocess.CalledProcessError as e:
            raise RemoteCommandError(' '.join(e.cmd), e.output) from e
        except subprocess.TimeoutExpired:
            raise RemoteCommandError(' '.join(cmd), f"Copy command timed out after {self.timeout} seconds")


class SSHCommandRunner(BaseCommandRunner):

    def __init__(self, board_ip: str, timeout: int = 5, keep_alive: int = 10):
        super().__init__()

        self.board_ip = board_ip
        self.timeout = int(timeout)
        self.keep_alive = int(keep_alive)
        self.ssh_options = [
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={self.timeout}",
        ]
        self.ssh_socket = os.path.join(tempfile.gettempdir(), f"ssh_mux_{board_ip.replace('.', '_')}")
        self._init_connection()

    def _init_connection(self):
        # Start a master connection that stays open
        subprocess.Popen([
            "ssh", "-MNf",
            "-o", f"ControlMaster=yes",
            "-o", f"ControlPath={self.ssh_socket}",
            "-o", f"ControlPersist={self.keep_alive}s",  # Keep alive for 10 seconds after last use
            f"root@{self.board_ip}"
        ] + self.ssh_options,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)

    def run_cmd(self, cmd: str | list[str]) -> str | None:
        if isinstance(cmd, str):
            cmd = cmd.split()
        try:
            result = subprocess.check_output(
                [
                    "ssh", "-T",
                    "-o", "ControlMaster=no",
                    "-o", f"ControlPath={self.ssh_socket}"
                ] + self.ssh_options +
                [f"root@{self.board_ip}"] + cmd,
                text=True,
                stderr=subprocess.STDOUT
            )
            return result
        except subprocess.CalledProcessError as e:
            raise RemoteCommandError(' '.join(e.cmd), e.stdout) from e
        
    def copy(self, src: str, dst: str, recursive: bool = False, board_dst: bool = False) -> None:
        cmd = ["scp"]
        if recursive:
            cmd.append("-r")
        if board_dst:
            dst = f"root@{self.board_ip}:{dst}"
        else:
            src = f"root@{self.board_ip}:{src}"
        cmd.extend([
            "-o", "ControlMaster=no",
            "-o", f"ControlPath={self.ssh_socket}",
            src,
            dst
        ])
        try:
            subprocess.check_output(
                cmd,
                text=True,
                stderr=subprocess.STDOUT
            )
        except subprocess.CalledProcessError as e:
            raise RemoteCommandError(' '.join(e.cmd), e.stdout) from e


if __name__ == "__main__":
    pass
