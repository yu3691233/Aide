import socket
import atexit
from network_utils import get_all_local_ips, is_physical_lan


def register_mdns_service(port=5000):
    try:
        local_ips = get_all_local_ips()
        local_ips = [ip for ip in local_ips if is_physical_lan(ip)]

        if not local_ips:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ips.append(s.getsockname()[0])
                s.close()
            except Exception:
                local_ips.append("127.0.0.1")

        print(f"[mDNS] Broadcasting IPs: {local_ips}", flush=True)

        from zeroconf import Zeroconf, ServiceInfo
        desc = {b'version': b'1.0.0', b'path': b'/'}

        info = ServiceInfo(
            "_aidelink._tcp.local.",
            "AideLinkService._aidelink._tcp.local.",
            addresses=[socket.inet_aton(ip) for ip in local_ips],
            port=port,
            properties=desc,
            server="aidelink-server.local."
        )

        zeroconf_obj = Zeroconf()
        zeroconf_obj.register_service(info)
        print(f"[mDNS] Successfully registered service. IPs: {local_ips}, Port: {port}", flush=True)

        def unregister():
            try:
                print("[mDNS] Unregistering service...", flush=True)
                zeroconf_obj.unregister_service(info)
                zeroconf_obj.close()
            except Exception:
                pass
        atexit.register(unregister)

    except Exception as e:
        import traceback
        print(f"[mDNS] Error registering service: {e}", flush=True)
        traceback.print_exc()
