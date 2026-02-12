"""
NetTools - Traceroute Service
Provides traceroute functionality with hop-by-hop analysis
"""

import subprocess
import re
import logging
import socket

logger = logging.getLogger(__name__)


def run_traceroute(target: str, max_hops: int = 30, timeout: int = 5) -> dict:
    """
    Run a traceroute to the specified target.
    Returns hop-by-hop data with latencies.

    Args:
        target: IP address or hostname to trace
        max_hops: Maximum number of hops (default 30)
        timeout: Timeout per hop in seconds (default 5)

    Returns:
        dict with keys:
        - target: original target
        - resolved_ip: resolved IP of target
        - hops: list of hop dicts
        - total_hops: number of hops
        - completed: whether trace reached destination
    """
    try:
        # Validate and resolve target
        target = target.strip()
        if not target:
            raise ValueError("Target is empty")

        # Basic input sanitization - only allow valid hostnames/IPs
        if not re.match(r'^[a-zA-Z0-9\.\-:]+$', target):
            raise ValueError(f"Invalid target: {target}")

        # Try to resolve hostname
        resolved_ip = None
        try:
            resolved_ip = socket.gethostbyname(target)
        except socket.gaierror:
            pass

        logger.info(f"Running traceroute to {target} (resolved: {resolved_ip})...")

        # Run traceroute command
        cmd = [
            'traceroute',
            '-n',               # No DNS resolution (faster)
            '-m', str(max_hops),
            '-w', str(timeout),
            '-q', '3',          # 3 queries per hop
            target
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max_hops * timeout + 10
        )

        # Parse output even if return code is non-zero (partial traces are valid)
        output = result.stdout
        if not output and result.stderr:
            # Try tracepath as fallback
            return _run_tracepath(target, max_hops)

        hops = _parse_traceroute_output(output)

        # Determine if trace completed (last hop matches target)
        completed = False
        if hops and resolved_ip:
            last_hop = hops[-1]
            if last_hop.get('ip') == resolved_ip:
                completed = True
        elif hops:
            completed = not hops[-1].get('timeout', False)

        result_data = {
            'target': target,
            'resolved_ip': resolved_ip or target,
            'hops': hops,
            'total_hops': len(hops),
            'completed': completed,
        }

        logger.info(f"Traceroute completed: {len(hops)} hops, completed={completed}")
        return result_data

    except subprocess.TimeoutExpired:
        logger.error(f"Traceroute to {target} timed out")
        raise Exception(f"Traceroute a {target} ha expirado (timeout)")
    except FileNotFoundError:
        # traceroute not installed, try tracepath
        logger.warning("traceroute not found, trying tracepath...")
        return _run_tracepath(target, max_hops)
    except ValueError as e:
        logger.error(f"Invalid target: {e}")
        raise
    except Exception as e:
        logger.error(f"Traceroute error: {e}")
        raise


def _run_tracepath(target: str, max_hops: int = 30) -> dict:
    """Fallback using tracepath (usually pre-installed on Ubuntu)."""
    try:
        cmd = ['tracepath', '-n', '-m', str(max_hops), target]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        output = result.stdout
        hops = _parse_tracepath_output(output)

        resolved_ip = None
        try:
            resolved_ip = socket.gethostbyname(target)
        except socket.gaierror:
            pass

        completed = False
        if hops and resolved_ip:
            last_hop = hops[-1]
            if last_hop.get('ip') == resolved_ip:
                completed = True

        return {
            'target': target,
            'resolved_ip': resolved_ip or target,
            'hops': hops,
            'total_hops': len(hops),
            'completed': completed,
        }

    except FileNotFoundError:
        logger.error("Neither traceroute nor tracepath found")
        raise Exception("traceroute/tracepath no está instalado en el servidor")
    except subprocess.TimeoutExpired:
        raise Exception(f"Tracepath a {target} ha expirado (timeout)")


def _parse_traceroute_output(output: str) -> list:
    """
    Parse standard traceroute output.
    Format:
     1  192.168.1.1  0.456 ms  0.321 ms  0.298 ms
     2  10.0.0.1  1.234 ms  1.456 ms  1.789 ms
     3  * * *
    """
    hops = []
    lines = output.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip header line (starts with "traceroute to")
        if line.lower().startswith('traceroute'):
            continue

        # Match hop number at start
        match = re.match(r'^\s*(\d+)\s+(.+)$', line)
        if not match:
            continue

        hop_num = int(match.group(1))
        rest = match.group(2).strip()

        # Check for complete timeout (* * *)
        if re.match(r'^[\*\s]+$', rest):
            hops.append({
                'hop': hop_num,
                'ip': None,
                'hostname': None,
                'latencies': [],
                'avg_latency': None,
                'min_latency': None,
                'max_latency': None,
                'loss': 100,
                'timeout': True,
            })
            continue

        # Extract IP and latencies
        # Pattern: IP ms ms ms (with possible * for individual timeouts)
        ip = None
        latencies = []

        # Find IP address in the line
        ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', rest)
        if ip_match:
            ip = ip_match.group(1)

        # Find all latency values (number followed by "ms")
        latency_matches = re.findall(r'([\d.]+)\s*ms', rest)
        latencies = [float(l) for l in latency_matches]

        # Count timeouts (asterisks)
        timeouts = rest.count('*')
        total_probes = len(latencies) + timeouts
        loss = round((timeouts / max(total_probes, 1)) * 100, 1) if total_probes > 0 else 0

        hop_data = {
            'hop': hop_num,
            'ip': ip,
            'hostname': None,
            'latencies': latencies,
            'avg_latency': round(sum(latencies) / len(latencies), 2) if latencies else None,
            'min_latency': round(min(latencies), 2) if latencies else None,
            'max_latency': round(max(latencies), 2) if latencies else None,
            'loss': loss,
            'timeout': False,
        }

        hops.append(hop_data)

    return hops


def _parse_tracepath_output(output: str) -> list:
    """
    Parse tracepath output.
    Format:
     1?: [LOCALHOST]     pmtu 1500
     1:  gateway         0.178ms
     1:  gateway         0.156ms
     2:  10.0.0.1        1.234ms
    """
    hops = {}
    lines = output.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match: N: IP/host latency
        match = re.match(r'^\s*(\d+)[:?]\s+(.+?)\s+([\d.]+)ms', line)
        if not match:
            # Check for "no reply" lines
            no_reply = re.match(r'^\s*(\d+)[:?]\s+no reply', line)
            if no_reply:
                hop_num = int(no_reply.group(1))
                if hop_num not in hops:
                    hops[hop_num] = {
                        'hop': hop_num,
                        'ip': None,
                        'hostname': None,
                        'latencies': [],
                        'timeout': True,
                    }
            continue

        hop_num = int(match.group(1))
        host = match.group(2).strip()
        latency = float(match.group(3))

        # Determine if host is IP or hostname
        ip = None
        hostname = None
        if re.match(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', host):
            ip = host
        elif host.startswith('[') and host.endswith(']'):
            continue  # Skip LOCALHOST entries
        else:
            hostname = host
            try:
                ip = socket.gethostbyname(host)
            except socket.gaierror:
                ip = host

        if hop_num not in hops:
            hops[hop_num] = {
                'hop': hop_num,
                'ip': ip,
                'hostname': hostname,
                'latencies': [],
                'timeout': False,
            }

        hops[hop_num]['latencies'].append(latency)
        if ip and not hops[hop_num].get('ip'):
            hops[hop_num]['ip'] = ip

    # Calculate statistics for each hop
    result = []
    for hop_num in sorted(hops.keys()):
        hop = hops[hop_num]
        latencies = hop['latencies']
        hop['avg_latency'] = round(sum(latencies) / len(latencies), 2) if latencies else None
        hop['min_latency'] = round(min(latencies), 2) if latencies else None
        hop['max_latency'] = round(max(latencies), 2) if latencies else None
        hop['loss'] = 100 if hop.get('timeout') and not latencies else 0
        result.append(hop)

    return result
