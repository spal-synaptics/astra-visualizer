import os
import subprocess
import tempfile


class SSHCommandError(BaseException):

    def __init__(self, cmd: str, output: str):
        self.cmd = cmd
        self.output = output
        super().__init__(f"Error running command \"{cmd}\":\n\t{output}")


class RemoteCommandRunner:

    def __init__(self, board_ip: str, timeout: int = 5):
        self.board_ip = board_ip
        self.timeout = int(timeout)

    def ssh_cmd(self, cmd: str | list[str]) -> str | None:
        if isinstance(cmd, str):
            cmd = cmd.split()
        try:
            result = subprocess.check_output(
                [
                    "ssh", "-T",
                    "-o", "BatchMode=yes",
                    "-o", f"ConnectTimeout={self.timeout}",
                    f"root@{self.board_ip}"
                ] + cmd,
                text=True,
                stderr=subprocess.STDOUT
            )
            print(f"Successfully executed command \"{' '.join(cmd)}\" on root@{self.board_ip}")
            return result
        except subprocess.CalledProcessError as e:
            raise SSHCommandError(' '.join(e.cmd), e.stdout) from e
        
    def scp_cmd(self, src: str, dst: str, recursive: bool = False, board_dst: bool = False) -> None:
        cmd = ["scp"]
        if recursive:
            cmd.append("-r")
        if board_dst:
            dst = f"root@{self.board_ip}:{dst}"
        else:
            src = f"root@{self.board_ip}:{src}"
        cmd.extend([
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={self.timeout}",
            src,
            dst
        ])
        try:
            subprocess.check_output(
                cmd,
                text=True,
                stderr=subprocess.STDOUT
            )
            print(f"Copied {src} to {dst}")
        except subprocess.CalledProcessError as e:
            raise SSHCommandError(' '.join(e.cmd), e.stdout) from e


class LowLatencyRemoteCommandRunner:

    def __init__(self, board_ip: str, timeout: int = 5, keep_alive: int = 10):
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

    def ssh_cmd(self, cmd: str | list[str]) -> str | None:
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
            raise SSHCommandError(' '.join(e.cmd), e.stdout) from e
        
    def scp_cmd(self, src: str, dst: str, recursive: bool = False, board_dst: bool = False) -> None:
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
            raise SSHCommandError(' '.join(e.cmd), e.stdout) from e


if __name__ == "__main__":
    pass
