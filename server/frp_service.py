import os
import json
import shutil
import subprocess
import atexit
from paths import BRIDGE_DIR, CONFIG_FILE
from json_utils import safe_read_json

_frp_proc = None
_frp_log_file = None


def is_frp_running():
    global _frp_proc
    if _frp_proc is None:
        return False
    return _frp_proc.poll() is None


def get_frp_status():
    running = is_frp_running()
    public_url = None
    try:
        cfg = safe_read_json(CONFIG_FILE, {})
        if isinstance(cfg, dict):
            proxies = cfg.get("frp", {}).get("proxies", [])
            if proxies:
                public_url = f"https://{proxies[0].get('custom_domains', '')}"
    except Exception:
        pass
    return {
        "running": running,
        "pid": _frp_proc.pid if running and _frp_proc else None,
        "public_url": public_url if running else None,
    }


def start_frp_client(force=False):
    global _frp_proc, _frp_log_file

    if is_frp_running():
        print("[FRP] Already running.", flush=True)
        return True

    # Do not kill every frpc on the machine.  Another project may own it;
    # AideLink only stops the child process tracked in ``_frp_proc``.

    if not os.path.exists(CONFIG_FILE):
        print("[FRP] No config.json found at startup.", flush=True)
        return False
    try:
        cfg = safe_read_json(CONFIG_FILE, {})
        if not isinstance(cfg, dict):
            cfg = {}
        frp_cfg = cfg.get("frp", {})
        if not force and not frp_cfg.get("enabled", False):
            print("[FRP] Client is disabled in config.json.", flush=True)
            return False

        frpc_exe_path = os.path.join(BRIDGE_DIR, "frpc.exe")
        if not os.path.exists(frpc_exe_path):
            _download_frpc(frpc_exe_path)

        server_addr = frp_cfg.get("server_addr", "")
        server_port = frp_cfg.get("server_port", 7000)
        token = frp_cfg.get("token", "")
        flask_local_port = cfg.get("flask_port", 5000)

        if not server_addr:
            print("[FRP] Server address is empty, skipping.", flush=True)
            return False

        proxies = _build_proxies(frp_cfg, flask_local_port)
        if not proxies:
            print("[FRP] No proxies configured, skipping.", flush=True)
            return False

        _write_frp_configs(proxies, server_addr, server_port, token)

        frpc_bin = _find_frpc()
        if not frpc_bin:
            print("[FRP] frpc executable not found in server directory or PATH.", flush=True)
            return False

        print(f"[FRP] Starting frpc client using {frpc_bin}...", flush=True)

        cmd = [frpc_bin, "-c", os.path.join(BRIDGE_DIR, "frpc_run.toml")]
        try:
            ver_output = subprocess.check_output([frpc_bin, "-v"], stderr=subprocess.STDOUT, timeout=2).decode().strip()
            print(f"[FRP] Detected frpc version: {ver_output}", flush=True)
            if any(ver_output.startswith(v) for v in ["0.4", "0.3", "0.2", "0.50", "0.51"]):
                cmd = [frpc_bin, "-c", os.path.join(BRIDGE_DIR, "frpc_run.ini")]
        except Exception as e:
            print(f"[FRP] Version check failed: {e}, defaulting to TOML configuration.", flush=True)

        log_path = os.path.join(BRIDGE_DIR, "frpc_run.log")
        try:
            if os.path.exists(log_path) and os.path.getsize(log_path) > 5 * 1024 * 1024:
                bak_path = log_path + ".bak"
                if os.path.exists(bak_path):
                    os.remove(bak_path)
                os.rename(log_path, bak_path)
        except Exception:
            pass

        _frp_log_file = open(log_path, "a", encoding="utf-8")
        _frp_proc = subprocess.Popen(
            cmd,
            cwd=BRIDGE_DIR,
            stdout=_frp_log_file,
            stderr=_frp_log_file,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        atexit.register(stop_frp_client)
        print(f"[FRP] frpc process started with PID {_frp_proc.pid}", flush=True)
        return True

    except Exception as e:
        print(f"[FRP] Failed to start frp client: {e}", flush=True)
        return False


def stop_frp_client():
    global _frp_proc, _frp_log_file
    if _frp_proc is None:
        return
    try:
        print("[FRP] Stopping frpc client...", flush=True)
        _frp_proc.terminate()
        _frp_proc.wait(timeout=3)
    except Exception:
        try:
            _frp_proc.kill()
        except Exception:
            pass
    _frp_proc = None
    if _frp_log_file:
        try:
            _frp_log_file.close()
        except Exception:
            pass
        _frp_log_file = None
    print("[FRP] Stopped.", flush=True)


def toggle_frp():
    if is_frp_running():
        stop_frp_client()
        return False
    else:
        return start_frp_client()


def _download_frpc(frpc_exe_path):
    import urllib.request
    import zipfile
    print("[FRP] frpc.exe not found. Attempting to download automatically...", flush=True)
    download_urls = [
        "https://mirror.ghproxy.com/https://github.com/fatedier/frp/releases/download/v0.54.0/frp_0.54.0_windows_amd64.zip",
        "https://github.com/fatedier/frp/releases/download/v0.54.0/frp_0.54.0_windows_amd64.zip"
    ]
    zip_path = os.path.join(BRIDGE_DIR, "frp.zip")
    for url in download_urls:
        try:
            print(f"[FRP] Downloading from {url}...", flush=True)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response, open(zip_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            print("[FRP] Extracting...", flush=True)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    if file_info.filename.endswith("frpc.exe"):
                        zip_ref.extract(file_info, BRIDGE_DIR)
                        extracted_path = os.path.join(BRIDGE_DIR, file_info.filename)
                        shutil.move(extracted_path, frpc_exe_path)
                        extracted_dir = os.path.dirname(extracted_path)
                        if extracted_dir != BRIDGE_DIR:
                            shutil.rmtree(extracted_dir)
                        break
            if os.path.exists(zip_path):
                os.remove(zip_path)
            print("[FRP] frpc.exe downloaded and installed successfully!", flush=True)
            return True
        except Exception as e:
            print(f"[FRP] Failed download from {url}: {e}", flush=True)
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except Exception:
                    pass
    print("[FRP] Could not download frpc.exe automatically.", flush=True)
    return False


def _build_proxies(frp_cfg, flask_local_port):
    proxies = frp_cfg.get("proxies")
    if not proxies:
        legacy_type = frp_cfg.get("type", "http")
        legacy_domains = frp_cfg.get("custom_domains", "")
        legacy_remote = frp_cfg.get("remote_port", 5000)
        return [{
            "name": "mengling-bridge",
            "type": legacy_type,
            "local_ip": "127.0.0.1",
            "local_port": flask_local_port,
            "custom_domains": legacy_domains,
            "remote_port": legacy_remote,
        }]
    normalized = []
    for p in proxies:
        if not isinstance(p, dict):
            continue
        normalized.append({
            "name": p.get("name") or f"proxy-{len(normalized)}",
            "type": p.get("type", "http"),
            "local_ip": p.get("local_ip", "127.0.0.1"),
            "local_port": int(p.get("local_port", flask_local_port)),
            "custom_domains": p.get("custom_domains", ""),
            "remote_port": int(p.get("remote_port", flask_local_port)),
        })
    return normalized


def _write_frp_configs(proxies, server_addr, server_port, token):
    proxy_toml_chunks = []
    proxy_ini_chunks = []
    for p in proxies:
        pname = p["name"]
        ptype = p["type"]
        plocal_ip = p["local_ip"]
        plocal_port = p["local_port"]
        pdomains = p["custom_domains"]
        premote_port = p["remote_port"]
        if ptype in ("http", "https"):
            proxy_toml_chunks.append(
                f'[[proxies]]\nname = "{pname}"\ntype = "{ptype}"\nlocalIP = "{plocal_ip}"\nlocalPort = {plocal_port}\ncustomDomains = ["{pdomains}"]'
            )
            proxy_ini_chunks.append(
                f'[{pname}]\ntype = {ptype}\nlocal_ip = {plocal_ip}\nlocal_port = {plocal_port}\ncustom_domains = {pdomains}'
            )
        else:
            proxy_toml_chunks.append(
                f'[[proxies]]\nname = "{pname}"\ntype = "tcp"\nlocalIP = "{plocal_ip}"\nlocalPort = {plocal_port}\nremotePort = {premote_port}'
            )
            proxy_ini_chunks.append(
                f'[{pname}]\ntype = tcp\nlocal_ip = {plocal_ip}\nlocal_port = {plocal_port}\nremote_port = {premote_port}'
            )

    proxy_toml = "\n\n".join(proxy_toml_chunks)
    proxy_ini = "\n\n".join(proxy_ini_chunks)

    toml_content = f'serverAddr = "{server_addr}"\nserverPort = {server_port}\nauth.method = "token"\nauth.token = "{token}"\n\n{proxy_toml}\n'
    ini_content = f'[common]\nserver_addr = {server_addr}\nserver_port = {server_port}\ntoken = {token}\n\n{proxy_ini}\n'

    with open(os.path.join(BRIDGE_DIR, "frpc_run.toml"), "w", encoding="utf-8") as f:
        f.write(toml_content)
    with open(os.path.join(BRIDGE_DIR, "frpc_run.ini"), "w", encoding="utf-8") as f:
        f.write(ini_content)


def _find_frpc():
    possible_bins = [
        os.path.join(BRIDGE_DIR, "frpc.exe"),
        os.path.join(BRIDGE_DIR, "frpc"),
        "frpc.exe",
        "frpc"
    ]
    for p in possible_bins:
        if os.path.exists(p) or shutil.which(p):
            return p
    return None
